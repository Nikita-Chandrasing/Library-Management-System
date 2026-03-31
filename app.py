import streamlit as st
import chromadb
from openai import OpenAI
from datetime import datetime, timedelta, date
import random
import os
import json

# =====================================================================
# CONFIG
# =====================================================================
CHROMA_DIR = "./chroma_store"

# =====================================================================
# DATABASE — seeded on first run, persisted after
# =====================================================================
@st.cache_resource
def get_db():
    """Initialize ChromaDB and seed catalog if empty."""
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    books = client.get_or_create_collection("library_books")

    if books.count() == 0:
        GENRES = ["Classic", "Romance", "Dystopian", "Sci-Fi", "Fantasy", "Mystery", "Thriller", "Non-Fiction"]
        AUTHORS = {
            "Classic": ["F. Scott Fitzgerald", "Jane Austen", "Mark Twain"],
            "Romance": ["Nicholas Sparks", "Julia Quinn", "Colleen Hoover"],
            "Dystopian": ["George Orwell", "Aldous Huxley", "Suzanne Collins"],
            "Sci-Fi": ["Isaac Asimov", "Philip K. Dick", "Arthur C. Clarke"],
            "Fantasy": ["J.K. Rowling", "J.R.R. Tolkien", "Brandon Sanderson"],
            "Mystery": ["Agatha Christie", "Arthur Conan Doyle", "Gillian Flynn"],
            "Thriller": ["Dan Brown", "Lee Child", "James Patterson"],
            "Non-Fiction": ["Yuval Noah Harari", "Malcolm Gladwell", "Michelle Obama"]
        }
        TITLES = {
            "Classic": ["The Great Gatsby", "Pride and Prejudice", "Adventures of Huckleberry Finn"],
            "Romance": ["The Notebook", "Bridgerton Series", "It Ends with Us"],
            "Dystopian": ["1984", "Brave New World", "The Hunger Games"],
            "Sci-Fi": ["Foundation", "Do Androids Dream of Electric Sheep?", "2001: A Space Odyssey"],
            "Fantasy": ["Harry Potter", "The Hobbit", "Mistborn"],
            "Mystery": ["Murder on the Orient Express", "Sherlock Holmes", "Gone Girl"],
            "Thriller": ["The Da Vinci Code", "Jack Reacher Series", "Along Came a Spider"],
            "Non-Fiction": ["Sapiens", "Outliers", "Becoming"]
        }

        book_data = []
        for genre in GENRES:
            for title, author in zip(TITLES[genre], AUTHORS[genre]):
                status = random.choice(["available"] * 8 + ["borrowed"] * 2)
                borrow_date = due_date = member_id = ""
                if status == "borrowed":
                    borrow_date = (datetime.now() - timedelta(days=random.randint(1, 10))).strftime("%Y-%m-%d")
                    due_date = (datetime.now() + timedelta(days=random.randint(4, 14))).strftime("%Y-%m-%d")
                    member_id = f"M{random.randint(1000, 9999)}"
                book_data.append({
                    "id": f"bk::{title.replace(' ', '_')}",
                    "document": f"{title} by {author} ({genre})",
                    "metadata": {
                        "book_title": title, "author": author, "genre": genre,
                        "isbn": str(random.randint(1000000000000, 9999999999999)),
                        "status": status, "member_id": member_id,
                        "borrow_date": borrow_date, "due_date": due_date,
                        "created": datetime.now().isoformat()
                    }
                })

        books.add(
            documents=[b["document"] for b in book_data],
            metadatas=[b["metadata"] for b in book_data],
            ids=[b["id"] for b in book_data]
        )

    return books

# =====================================================================
# TOOL FUNCTIONS (Library Operations)
# =====================================================================
def get_all_books():
    books = get_db()
    results = books.get()
    book_options = []
    for id, meta, doc in zip(results['ids'], results['metadatas'], results['documents']):
        label = f"{meta.get('book_title')} by {meta.get('author')} ({meta.get('genre')})"
        book_options.append({"id": id, "label": label, "meta": meta, "doc": doc})
    return book_options

def get_borrowed_books(member_id=None):
    all_books = get_all_books()
    borrowed = [b for b in all_books if b["meta"].get("status") == "borrowed"]
    if member_id:
        borrowed = [b for b in borrowed if b["meta"].get("member_id") == member_id]
    return borrowed

def borrow_book(book_id, member_id):
    books = get_db()
    result = books.get(ids=[book_id])
    if not result['ids']:
        return {"success": False, "message": "Book not found"}
    meta = result['metadatas'][0]
    doc = result['documents'][0]
    if meta.get('status') == "borrowed":
        return hold_book(book_id, member_id)
    borrow_date = datetime.now().strftime("%Y-%m-%d")
    due_date = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
    meta.update({"status": "borrowed", "borrow_date": borrow_date, "due_date": due_date, "member_id": member_id})
    books.upsert(documents=[doc], metadatas=[meta], ids=[book_id])
    return {"success": True, "message": f"You borrowed '{meta['book_title']}' successfully!", "due_date": due_date}

def return_book(book_id):
    books = get_db()
    result = books.get(ids=[book_id])
    if not result['ids']:
        return {"success": False, "message": "Book not found"}
    meta = result['metadatas'][0]
    doc = result['documents'][0]
    if meta.get('status') != "borrowed":
        return {"success": False, "message": "Book is not currently borrowed"}
    due_date = datetime.strptime(meta['due_date'], "%Y-%m-%d").date()
    today = date.today()
    late_fee = max(0, (today - due_date).days * 0.50) if today > due_date else 0
    meta.update({"status": "available", "borrow_date": "", "due_date": "", "member_id": ""})
    books.upsert(documents=[doc], metadatas=[meta], ids=[book_id])
    msg = f"Returned '{meta['book_title']}' successfully!"
    if late_fee > 0:
        msg += f" Late fee: ${late_fee:.2f}"
    return {"success": True, "message": msg}

def renew_loan(book_id):
    books = get_db()
    result = books.get(ids=[book_id])
    if not result['ids']:
        return {"success": False, "message": "Book not found"}
    meta = result['metadatas'][0]
    doc = result['documents'][0]
    if meta.get('status') != "borrowed":
        return {"success": False, "message": "Book is not borrowed"}
    new_due = (datetime.strptime(meta['due_date'], "%Y-%m-%d") + timedelta(days=14)).strftime("%Y-%m-%d")
    meta['due_date'] = new_due
    books.upsert(documents=[doc], metadatas=[meta], ids=[book_id])
    return {"success": True, "message": f"Renewed loan for '{meta['book_title']}' successfully!", "due_date": new_due}

def recommend_books(book_id):
    all_books = get_all_books()
    base = next((b for b in all_books if b["id"] == book_id), None)
    if not base:
        return []
    base_genre = base["meta"]["genre"]
    base_author = base["meta"]["author"]
    recs = [b for b in all_books if b["id"] != book_id and (b["meta"]["genre"] == base_genre or b["meta"]["author"] == base_author)]
    random.shuffle(recs)
    return recs[:3]

def hold_book(book_id, member_id):
    books = get_db()
    result = books.get(ids=[book_id])
    if not result['ids']:
        return {"success": False, "message": "Book not found"}
    meta = result['metadatas'][0]
    doc = result['documents'][0]
    waitlist_raw = meta.get('waitlist', '')
    waitlist = waitlist_raw.split(',') if waitlist_raw else []
    if member_id in waitlist:
        return {"success": False, "message": "You are already on the waitlist for this book"}
    waitlist.append(member_id)
    meta['waitlist'] = ','.join(waitlist)
    books.upsert(documents=[doc], metadatas=[meta], ids=[book_id])
    return {"success": True, "message": f"You've been added to the waitlist for '{meta['book_title']}'. Position: #{len(waitlist)}"}

# =====================================================================
# OPENAI FUNCTION DEFINITIONS
# =====================================================================
TOOLS = [
    {"type":"function","function":{"name":"borrow_book","description":"Borrow a book from the library","parameters":{"type":"object","properties":{"book_id":{"type":"string"},"member_id":{"type":"string"}},"required":["book_id","member_id"]}}},
    {"type":"function","function":{"name":"return_book","description":"Return a borrowed book","parameters":{"type":"object","properties":{"book_id":{"type":"string"}},"required":["book_id"]}}},
    {"type":"function","function":{"name":"renew_loan","description":"Renew a borrowed book for 14 more days","parameters":{"type":"object","properties":{"book_id":{"type":"string"},"member_id":{"type":"string"}},"required":[]}}},
    {"type":"function","function":{"name":"recommend_books","description":"Recommend similar books","parameters":{"type":"object","properties":{"book_id":{"type":"string"}},"required":["book_id"]}}},
    {"type":"function","function":{"name":"hold_book","description":"Place a hold on a borrowed book","parameters":{"type":"object","properties":{"book_id":{"type":"string"},"member_id":{"type":"string"}},"required":["book_id","member_id"]}}},
    {"type":"function","function":{"name":"get_borrowed_books","description":"List all borrowed books, optionally for a member","parameters":{"type":"object","properties":{"member_id":{"type":"string"}},"required":[]}}}
]

def chat_with_tools(messages, model="gpt-4o-mini"):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "❌ API key not set. Please add it to your Streamlit secrets."
    client = OpenAI(api_key=api_key)
    system_msg = {
        "role": "system",
        "content": (
            f"You are a helpful Library Assistant. Today's date: {date.today()}.\n"
            "- Always ask for member ID if not provided.\n"
            "- Be friendly and helpful.\n"
            "- Recommend books when asked.\n"
            "- Borrowing loans last 14 days.\n"
            "- You have access to borrowed books via get_borrowed_books.\n"
            "- When a user asks about a book, use the book_id format: bk::Title_With_Underscores"
        )
    }
    response = client.chat.completions.create(
        model=model, messages=[system_msg] + messages, tools=TOOLS, tool_choice="auto"
    )
    message = response.choices[0].message
    if message.tool_calls:
        tool_results = []
        for tool_call in message.tool_calls:
            fn = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            if fn == "borrow_book":
                result = borrow_book(**args)
            elif fn == "return_book":
                result = return_book(**args)
            elif fn == "renew_loan":
                book_id = args.get("book_id")
                member_id = args.get("member_id")
                if not book_id and member_id:
                    borrowed = get_borrowed_books(member_id)
                    book_id = borrowed[0]["id"] if borrowed else None
                result = renew_loan(book_id) if book_id else {"success": False, "message": "No borrowed books found"}
            elif fn == "recommend_books":
                result = recommend_books(**args)
            elif fn == "hold_book":
                result = hold_book(**args)
            elif fn == "get_borrowed_books":
                borrowed = get_borrowed_books(args.get("member_id"))
                result = [{"title": b["meta"]["book_title"], "author": b["meta"]["author"], "id": b["id"], "due_date": b["meta"]["due_date"]} for b in borrowed]
            else:
                result = {"error": "Unknown function"}
            tool_results.append({
                "role": "tool", "tool_call_id": tool_call.id,
                "name": fn, "content": json.dumps(result)
            })
        messages.append({
            "role": message.role, "content": message.content or "",
            "tool_calls": [{"id": tc.id, "type": tc.type, "function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in message.tool_calls]
        })
        messages.extend(tool_results)
        final = client.chat.completions.create(model=model, messages=[system_msg] + messages)
        return final.choices[0].message.content
    return message.content

# =====================================================================
# STREAMLIT UI
# =====================================================================
def main():
    st.set_page_config(page_title="Library Assistant", layout="wide")
    st.title("📚 Library Assistant")
    st.caption("Manage your library and chat with the AI Assistant")

    # --- SIDEBAR: model selector ---
    with st.sidebar:
        st.header("⚙️ Settings")
        model_choice = st.selectbox(
            "AI Model",
            ["gpt-4o-mini", "gpt-4o"],
            index=0,
            help="gpt-4o-mini is faster and cheaper; gpt-4o is more capable"
        )
        st.session_state.selected_model = model_choice
        st.divider()
        st.markdown("**What I can help with:**")
        st.markdown("- 📘 Borrow a book\n- 📚 Search catalog\n- 📗 Return a book\n- 📒 Renew a loan\n- 💡 Get recommendations\n- 📕 Place a hold")
        st.divider()
        st.caption("Loan period: 14 days | Late fee: $0.50/day")

    get_db()

    if 'chat_messages' not in st.session_state:
        st.session_state.chat_messages = []
    if 'selected_model' not in st.session_state:
        st.session_state.selected_model = "gpt-4o-mini"

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "📘 Borrow", "📚 Search", "📗 Return", "📒 Renew",
        "💡 Recommend", "📕 Hold", "🤖 Chat with AI"
    ])

    with tab1:
        st.subheader("📘 Borrow a Book")
        all_books = get_all_books()
        available = [b for b in all_books if b["meta"]["status"] == "available"]
        if available:
            selected = st.selectbox("Select a book:", [b["label"] for b in available])
            member_id = st.text_input("Member ID:", key="borrow_member")
            if st.button("Confirm Borrow"):
                if member_id:
                    sid = next(b["id"] for b in available if b["label"] == selected)
                    result = borrow_book(sid, member_id)
                    st.success(f"{result['message']} Due: {result.get('due_date', '')}") if result["success"] else st.error(result["message"])
                else:
                    st.warning("Please enter your Member ID.")
        else:
            st.info("No books currently available.")

    with tab2:
        st.subheader("📚 Search Catalog")
        all_books = get_all_books()
        search = st.text_input("Search by title, author, or genre:")
        results = [b for b in all_books if search.lower() in b["label"].lower()] if search else all_books
        for b in results:
            meta = b["meta"]
            status_icon = "✅" if meta["status"] == "available" else "❌"
            st.markdown(f"{status_icon} **{meta['book_title']}** by {meta['author']} ({meta['genre']}) — *{meta['status']}*")

    with tab3:
        st.subheader("📗 Return a Book")
        member_id = st.text_input("Member ID:", key="return_member")
        if member_id:
            borrowed_by_user = [b for b in get_all_books() if b["meta"].get("member_id") == member_id]
            if borrowed_by_user:
                selected = st.selectbox("Select a book to return:", [b["label"] for b in borrowed_by_user])
                if st.button("Return"):
                    sid = next(b["id"] for b in borrowed_by_user if b["label"] == selected)
                    result = return_book(sid)
                    st.success(result["message"])
                    recs = recommend_books(sid)
                    if recs:
                        st.markdown("**💡 You might also like:**")
                        for r in recs:
                            st.markdown(f"- **{r['meta']['book_title']}** by {r['meta']['author']}")
            else:
                st.info("No borrowed books found for this Member ID.")

    with tab4:
        st.subheader("📒 Renew Loan")
        member_id = st.text_input("Member ID:", key="renew_member")
        if member_id:
            borrowed_by_user = [b for b in get_all_books() if b["meta"].get("member_id") == member_id]
            if borrowed_by_user:
                selected = st.selectbox("Select a book to renew:", [b["label"] for b in borrowed_by_user])
                if st.button("Renew"):
                    sid = next(b["id"] for b in borrowed_by_user if b["label"] == selected)
                    result = renew_loan(sid)
                    st.success(f"{result['message']} New due date: {result.get('due_date', '')}") if result["success"] else st.error(result["message"])
            else:
                st.info("No borrowed books found for this Member ID.")

    with tab5:
        st.subheader("💡 Book Recommendations")
        all_books = get_all_books()
        selected = st.selectbox("Select a book you liked:", [b["label"] for b in all_books])
        sid = next(b["id"] for b in all_books if b["label"] == selected)
        recs = recommend_books(sid)
        if recs:
            for r in recs:
                st.markdown(f"- **{r['meta']['book_title']}** by {r['meta']['author']} ({r['meta']['genre']})")
        else:
            st.info("No recommendations found.")

    with tab6:
        st.subheader("📕 Place a Hold")
        borrowed = [b for b in get_all_books() if b["meta"]["status"] == "borrowed"]
        if borrowed:
            selected = st.selectbox("Select a book to hold:", [b["label"] for b in borrowed])
            member_id = st.text_input("Member ID:", key="hold_member")
            if st.button("Place Hold"):
                if member_id:
                    sid = next(b["id"] for b in borrowed if b["label"] == selected)
                    result = hold_book(sid, member_id)
                    st.success(result["message"]) if result["success"] else st.error(result["message"])
                else:
                    st.warning("Please enter your Member ID.")
        else:
            st.info("All books are currently available — no holds needed!")

    with tab7:
        st.subheader("🤖 Chat with AI Assistant")
        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
        if prompt := st.chat_input("Ask me anything about library books..."):
            st.session_state.chat_messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    response = chat_with_tools(st.session_state.chat_messages, model=st.session_state.selected_model)
                st.markdown(response)
            st.session_state.chat_messages.append({"role": "assistant", "content": response})

if __name__ == "__main__":
    main()
