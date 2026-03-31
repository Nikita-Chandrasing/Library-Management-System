import streamlit as st
from datetime import datetime, timedelta
import chromadb
import os
import json
from openai import OpenAI

# ============================================================================
# PAGE CONFIG — must be first Streamlit call
# ============================================================================
st.set_page_config(
    page_title="📚 Library Management Chatbot",
    page_icon="📚",
    layout="wide"
)

# ============================================================================
# CONFIG
# ============================================================================
CHROMA_DIR = "./chroma_store"
LATE_FEE_PER_DAY = 0.25   # $0.25 per day overdue
MAX_RENEWALS = 2
LOAN_PERIOD_DAYS = 14

# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================
@st.cache_resource
def get_db():
    """Initialize ChromaDB and seed with sample data if empty."""
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_or_create_collection("library_books")

    # Only seed if collection is empty
    if collection.count() == 0:
        seed_records = [
            {
                "id": "bk::M001::The Great Gatsby::2025-10-01",
                "doc": "Borrow record: The Great Gatsby",
                "meta": {
                    "member_id": "M001", "book_title": "The Great Gatsby",
                    "author": "F. Scott Fitzgerald", "genre": "Classic",
                    "isbn": "978-0743273565", "borrow_date": "2025-10-01",
                    "due_date": "2025-10-15", "status": "borrowed",
                    "renewals": "0", "created": datetime.now().isoformat()
                }
            },
            {
                "id": "bk::M002::1984::2025-10-02",
                "doc": "Borrow record: 1984",
                "meta": {
                    "member_id": "M002", "book_title": "1984",
                    "author": "George Orwell", "genre": "Dystopian",
                    "isbn": "978-0451524935", "borrow_date": "2025-10-02",
                    "due_date": "2025-10-16", "status": "borrowed",
                    "renewals": "0", "created": datetime.now().isoformat()
                }
            },
            {
                "id": "bk::M003::Pride and Prejudice::2025-10-03",
                "doc": "Borrow record: Pride and Prejudice",
                "meta": {
                    "member_id": "M003", "book_title": "Pride and Prejudice",
                    "author": "Jane Austen", "genre": "Romance",
                    "isbn": "978-0141439518", "borrow_date": "2025-10-03",
                    "due_date": "2025-10-17", "status": "returned",
                    "renewals": "0", "created": datetime.now().isoformat()
                }
            },
            {
                "id": "bk::M004::Dune::2025-10-05",
                "doc": "Borrow record: Dune",
                "meta": {
                    "member_id": "M004", "book_title": "Dune",
                    "author": "Frank Herbert", "genre": "Science Fiction",
                    "isbn": "978-0441013593", "borrow_date": "2025-10-05",
                    "due_date": "2025-10-19", "status": "borrowed",
                    "renewals": "1", "created": datetime.now().isoformat()
                }
            },
        ]
        collection.add(
            documents=[r["doc"] for r in seed_records],
            metadatas=[r["meta"] for r in seed_records],
            ids=[r["id"] for r in seed_records]
        )

    return collection


# ============================================================================
# USE CASE 1 — BORROW BOOK
# ============================================================================
def borrow_book(member_id: str, book_title: str, genre: str,
                author: str = "Unknown", isbn: str = ""):
    """Check out a book to a member. Returns error if already borrowed."""
    db = get_db()
    borrow_date = datetime.now().strftime("%Y-%m-%d")
    due_date = (datetime.now() + timedelta(days=LOAN_PERIOD_DAYS)).strftime("%Y-%m-%d")
    record_id = f"bk::{member_id}::{book_title}::{borrow_date}"

    # Check if this book is already borrowed by anyone
    try:
        existing = db.get(
            where={"$and": [
                {"book_title": {"$eq": book_title}},
                {"status": {"$eq": "borrowed"}}
            ]}
        )
        if existing["ids"]:
            return {
                "success": False,
                "error": f"'{book_title}' is currently checked out. Would you like to place a hold instead?"
            }
    except Exception:
        pass

    metadata = {
        "member_id": member_id, "book_title": book_title,
        "author": author, "genre": genre, "isbn": isbn,
        "borrow_date": borrow_date, "due_date": due_date,
        "status": "borrowed", "renewals": "0",
        "created": datetime.now().isoformat()
    }

    db.add(
        documents=[f"Borrow record: {book_title}"],
        metadatas=[metadata],
        ids=[record_id]
    )

    return {
        "success": True,
        "record_id": record_id,
        "borrow_date": borrow_date,
        "due_date": due_date,
        "message": f"✅ '{book_title}' checked out to member {member_id}. Due back by {due_date}."
    }


# ============================================================================
# USE CASE 2 — SEARCH CATALOG
# ============================================================================
def search_catalog(title: str = None, author: str = None,
                   genre: str = None, available_only: bool = False):
    """Search the library catalog by title, author, genre, or availability."""
    db = get_db()

    try:
        # Build filter conditions
        conditions = []
        if genre:
            conditions.append({"genre": {"$eq": genre}})
        if available_only:
            conditions.append({"status": {"$eq": "returned"}})

        if conditions:
            where = {"$and": conditions} if len(conditions) > 1 else conditions[0]
            results = db.get(where=where)
        else:
            results = db.get()

        if not results["ids"]:
            return {"results": [], "message": "No books found matching your search."}

        # Filter by title/author locally (ChromaDB string contains not supported)
        books = []
        for i, meta in enumerate(results["metadatas"]):
            if title and title.lower() not in meta.get("book_title", "").lower():
                continue
            if author and author.lower() not in meta.get("author", "").lower():
                continue
            books.append({
                "title": meta.get("book_title"),
                "author": meta.get("author", "Unknown"),
                "genre": meta.get("genre"),
                "isbn": meta.get("isbn", "N/A"),
                "status": meta.get("status"),
                "due_date": meta.get("due_date") if meta.get("status") == "borrowed" else None
            })

        return {"results": books, "count": len(books)}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# USE CASE 3 — RETURN BOOK
# ============================================================================
def return_book(member_id: str, book_title: str, borrow_date: str):
    """Process a book return and calculate any late fees."""
    db = get_db()
    record_id = f"bk::{member_id}::{book_title}::{borrow_date}"

    try:
        existing = db.get(ids=[record_id])
    except Exception:
        return {"success": False, "error": f"No borrow record found for '{book_title}' (member {member_id}, borrowed {borrow_date})."}

    if not existing["ids"]:
        return {"success": False, "error": "Borrow record not found. Please verify your member ID and borrow date."}

    meta = existing["metadatas"][0]
    if meta.get("status") == "returned":
        return {"success": False, "error": f"'{book_title}' has already been returned."}

    # Calculate late fee
    due_date = datetime.strptime(meta["due_date"], "%Y-%m-%d")
    today = datetime.now()
    late_fee = 0.0
    days_late = 0

    if today > due_date:
        days_late = (today - due_date).days
        late_fee = round(days_late * LATE_FEE_PER_DAY, 2)

    # Update status to returned
    updated_meta = dict(meta)
    updated_meta["status"] = "returned"
    updated_meta["return_date"] = today.strftime("%Y-%m-%d")
    updated_meta["late_fee"] = str(late_fee)

    db.update(ids=[record_id], metadatas=[updated_meta])

    result = {
        "success": True,
        "book_title": book_title,
        "return_date": today.strftime("%Y-%m-%d"),
        "days_late": days_late,
        "late_fee": late_fee
    }
    if late_fee > 0:
        result["message"] = f"📚 '{book_title}' returned. Late fee: ${late_fee:.2f} ({days_late} days overdue)."
    else:
        result["message"] = f"✅ '{book_title}' returned on time. Thank you!"

    return result


# ============================================================================
# USE CASE 4 — RENEW LOAN
# ============================================================================
def renew_loan(member_id: str, book_title: str, borrow_date: str):
    """Extend a loan by LOAN_PERIOD_DAYS. Max renewals enforced."""
    db = get_db()
    record_id = f"bk::{member_id}::{book_title}::{borrow_date}"

    try:
        existing = db.get(ids=[record_id])
    except Exception:
        return {"success": False, "error": "Borrow record not found."}

    if not existing["ids"]:
        return {"success": False, "error": "No active loan found for this book and member."}

    meta = existing["metadatas"][0]
    if meta.get("status") != "borrowed":
        return {"success": False, "error": f"'{book_title}' is not currently checked out."}

    renewals = int(meta.get("renewals", "0"))
    if renewals >= MAX_RENEWALS:
        return {
            "success": False,
            "error": f"Maximum renewals ({MAX_RENEWALS}) reached for '{book_title}'. Please return and re-borrow."
        }

    # Extend due date
    current_due = datetime.strptime(meta["due_date"], "%Y-%m-%d")
    new_due = current_due + timedelta(days=LOAN_PERIOD_DAYS)
    new_due_str = new_due.strftime("%Y-%m-%d")

    updated_meta = dict(meta)
    updated_meta["due_date"] = new_due_str
    updated_meta["renewals"] = str(renewals + 1)

    db.update(ids=[record_id], metadatas=[updated_meta])

    return {
        "success": True,
        "book_title": book_title,
        "new_due_date": new_due_str,
        "renewals_used": renewals + 1,
        "renewals_remaining": MAX_RENEWALS - (renewals + 1),
        "message": f"✅ '{book_title}' renewed. New due date: {new_due_str}. ({MAX_RENEWALS - renewals - 1} renewal(s) remaining)"
    }


# ============================================================================
# CUSTOM USE CASE 1 — BOOK RECOMMENDATIONS
# ============================================================================
def recommend_books(genre: str = None, member_id: str = None):
    """
    Recommend books based on genre preference or a member's borrow history.
    If member_id is provided, analyzes their history to suggest genres they haven't tried.
    """
    db = get_db()

    # Curated recommendation catalog (would be a larger dataset in production)
    catalog = {
        "Classic": [
            {"title": "To Kill a Mockingbird", "author": "Harper Lee"},
            {"title": "The Catcher in the Rye", "author": "J.D. Salinger"},
            {"title": "Of Mice and Men", "author": "John Steinbeck"},
        ],
        "Dystopian": [
            {"title": "Brave New World", "author": "Aldous Huxley"},
            {"title": "The Handmaid's Tale", "author": "Margaret Atwood"},
            {"title": "Fahrenheit 451", "author": "Ray Bradbury"},
        ],
        "Science Fiction": [
            {"title": "The Martian", "author": "Andy Weir"},
            {"title": "Ender's Game", "author": "Orson Scott Card"},
            {"title": "Foundation", "author": "Isaac Asimov"},
        ],
        "Romance": [
            {"title": "Jane Eyre", "author": "Charlotte Brontë"},
            {"title": "Sense and Sensibility", "author": "Jane Austen"},
            {"title": "The Notebook", "author": "Nicholas Sparks"},
        ],
        "Mystery": [
            {"title": "Gone Girl", "author": "Gillian Flynn"},
            {"title": "The Girl with the Dragon Tattoo", "author": "Stieg Larsson"},
            {"title": "And Then There Were None", "author": "Agatha Christie"},
        ],
        "Fantasy": [
            {"title": "The Name of the Wind", "author": "Patrick Rothfuss"},
            {"title": "A Wizard of Earthsea", "author": "Ursula K. Le Guin"},
            {"title": "The Way of Kings", "author": "Brandon Sanderson"},
        ],
    }

    # If member_id given, analyze their borrow history
    history_genres = []
    if member_id:
        try:
            history = db.get(where={"member_id": {"$eq": member_id}})
            history_genres = list({m.get("genre") for m in history["metadatas"] if m.get("genre")})
        except Exception:
            pass

    # Select genre to recommend from
    target_genre = genre
    if not target_genre and history_genres:
        target_genre = history_genres[0]  # Use most recent genre if no preference given

    if target_genre and target_genre in catalog:
        recs = catalog[target_genre]
        return {
            "success": True,
            "genre": target_genre,
            "recommendations": recs,
            "based_on_history": bool(member_id and not genre),
            "message": f"📖 Top picks in {target_genre} for you!"
        }
    else:
        # Return a mix across genres
        mixed = []
        for g, books in list(catalog.items())[:3]:
            mixed.append({"genre": g, **books[0]})
        return {
            "success": True,
            "genre": "Mixed",
            "recommendations": mixed,
            "message": "📖 Here's a mix of popular picks across genres!"
        }


# ============================================================================
# CUSTOM USE CASE 2 — HOLD / WAITLIST
# ============================================================================
def place_hold(member_id: str, book_title: str):
    """
    Place a hold on a currently borrowed book.
    Member will be notified when it's available. Queue position tracked.
    """
    db = get_db()

    # Check if book is actually borrowed (hold only makes sense if unavailable)
    try:
        borrowed = db.get(
            where={"$and": [
                {"book_title": {"$eq": book_title}},
                {"status": {"$eq": "borrowed"}}
            ]}
        )
    except Exception:
        borrowed = {"ids": []}

    if not borrowed["ids"]:
        return {
            "success": False,
            "message": f"'{book_title}' appears to be available — you can borrow it directly! No hold needed."
        }

    # Check if member already has a hold on this book
    hold_id = f"hold::{member_id}::{book_title}"
    try:
        existing_hold = db.get(ids=[hold_id])
        if existing_hold["ids"]:
            meta = existing_hold["metadatas"][0]
            return {
                "success": False,
                "message": f"You already have a hold on '{book_title}' (position #{meta.get('queue_position', '?')})."
            }
    except Exception:
        pass

    # Count existing holds to determine queue position
    try:
        existing_holds = db.get(
            where={"$and": [
                {"book_title": {"$eq": book_title}},
                {"status": {"$eq": "on_hold"}}
            ]}
        )
        queue_position = len(existing_holds["ids"]) + 1
    except Exception:
        queue_position = 1

    # Get due date of current loan to estimate availability
    due_date = borrowed["metadatas"][0].get("due_date", "unknown") if borrowed["metadatas"] else "unknown"

    metadata = {
        "member_id": member_id,
        "book_title": book_title,
        "status": "on_hold",
        "queue_position": str(queue_position),
        "hold_date": datetime.now().strftime("%Y-%m-%d"),
        "estimated_available": due_date,
        "created": datetime.now().isoformat()
    }

    db.add(
        documents=[f"Hold record: {book_title}"],
        metadatas=[metadata],
        ids=[hold_id]
    )

    return {
        "success": True,
        "book_title": book_title,
        "member_id": member_id,
        "queue_position": queue_position,
        "estimated_available": due_date,
        "message": f"📌 Hold placed on '{book_title}'! You're #{queue_position} in line. Estimated available: {due_date}."
    }


# ============================================================================
# OPENAI TOOL DEFINITIONS
# ============================================================================
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "borrow_book",
            "description": "Check out a book from the library for a member. Call this when a user wants to borrow or check out a book.",
            "parameters": {
                "type": "object",
                "properties": {
                    "member_id": {"type": "string", "description": "The library member ID (e.g. M001)"},
                    "book_title": {"type": "string", "description": "Title of the book to borrow"},
                    "genre": {"type": "string", "description": "Genre of the book (e.g. Classic, Science Fiction)"},
                    "author": {"type": "string", "description": "Author of the book"},
                    "isbn": {"type": "string", "description": "ISBN of the book if known"}
                },
                "required": ["member_id", "book_title", "genre"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_catalog",
            "description": "Search the library catalog for books. Use this to find books by title, author, genre, or to check availability.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Book title to search for (partial match supported)"},
                    "author": {"type": "string", "description": "Author name to search for"},
                    "genre": {"type": "string", "description": "Genre to filter by"},
                    "available_only": {"type": "boolean", "description": "If true, only show books currently available (not borrowed)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "return_book",
            "description": "Process the return of a borrowed book. Calculates late fees if overdue.",
            "parameters": {
                "type": "object",
                "properties": {
                    "member_id": {"type": "string", "description": "The library member ID"},
                    "book_title": {"type": "string", "description": "Title of the book being returned"},
                    "borrow_date": {"type": "string", "description": "The date the book was originally borrowed (YYYY-MM-DD)"}
                },
                "required": ["member_id", "book_title", "borrow_date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "renew_loan",
            "description": "Renew (extend) an existing book loan. Maximum 2 renewals allowed per loan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "member_id": {"type": "string", "description": "The library member ID"},
                    "book_title": {"type": "string", "description": "Title of the book to renew"},
                    "borrow_date": {"type": "string", "description": "The original borrow date (YYYY-MM-DD)"}
                },
                "required": ["member_id", "book_title", "borrow_date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_books",
            "description": "Recommend books to a member based on genre preference or their borrowing history.",
            "parameters": {
                "type": "object",
                "properties": {
                    "genre": {"type": "string", "description": "Genre to get recommendations for (e.g. Mystery, Fantasy, Science Fiction)"},
                    "member_id": {"type": "string", "description": "Member ID to personalize recommendations based on borrow history"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "place_hold",
            "description": "Place a waitlist hold on a book that is currently borrowed by another member.",
            "parameters": {
                "type": "object",
                "properties": {
                    "member_id": {"type": "string", "description": "The library member ID placing the hold"},
                    "book_title": {"type": "string", "description": "Title of the book to place a hold on"}
                },
                "required": ["member_id", "book_title"]
            }
        }
    }
]

TOOL_MAP = {
    "borrow_book": borrow_book,
    "search_catalog": search_catalog,
    "return_book": return_book,
    "renew_loan": renew_loan,
    "recommend_books": recommend_books,
    "place_hold": place_hold,
}

SYSTEM_PROMPT = """You are a friendly and efficient library assistant for a public library management system.

You help members with:
1. **Borrowing books** — check out books, confirm due dates (14-day loan period)
2. **Searching the catalog** — find books by title, author, genre, or availability
3. **Returning books** — process returns and inform members of any late fees ($0.25/day)
4. **Renewing loans** — extend due dates (max 2 renewals per book)
5. **Book recommendations** — suggest books based on genre or member history
6. **Placing holds** — join the waitlist for currently borrowed books

**Business rules:**
- Loan period: 14 days
- Late fee: $0.25 per day overdue
- Maximum renewals: 2 per book
- A book cannot be borrowed if already checked out — offer a hold instead

**Conversation style:**
- Be warm, helpful, and concise
- Always confirm actions clearly (what was done, relevant dates, any fees)
- If information is missing, ask for it naturally — don't list all missing fields at once
- Use the member's name or ID when confirming transactions
- Format responses cleanly with relevant emojis for readability

When a user's request is ambiguous, ask a single clarifying question before proceeding."""


# ============================================================================
# CHAT WITH TOOLS — OPENAI FUNCTION CALLING LOOP
# ============================================================================
def chat_with_tools(messages: list, model: str) -> str:
    """Send messages to OpenAI, handle tool calls, return final response."""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Build the full message list with system prompt
    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

    # Step 1: Send to OpenAI
    response = client.chat.completions.create(
        model=model,
        messages=full_messages,
        tools=TOOLS,
        tool_choice="auto"
    )

    response_message = response.choices[0].message

    # Step 2: Check for tool calls
    if not response_message.tool_calls:
        return response_message.content

    # Step 3: Execute all tool calls
    full_messages.append(response_message)

    for tool_call in response_message.tool_calls:
        fn_name = tool_call.function.name
        fn_args = json.loads(tool_call.function.arguments)

        if fn_name in TOOL_MAP:
            result = TOOL_MAP[fn_name](**fn_args)
        else:
            result = {"error": f"Unknown function: {fn_name}"}

        # Step 4: Add tool result to messages
        full_messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": json.dumps(result)
        })

    # Step 5: Get final response with tool results
    final_response = client.chat.completions.create(
        model=model,
        messages=full_messages,
        tools=TOOLS,
        tool_choice="none"  # Don't call tools again on final pass
    )

    return final_response.choices[0].message.content


# ============================================================================
# STREAMLIT UI
# ============================================================================
def main():
    st.title("📚 Library Management Chatbot")
    st.caption("Borrow, return, renew, search, get recommendations, and place holds — powered by OpenAI + ChromaDB")

    # Sidebar — model selection + info
    with st.sidebar:
        st.header("⚙️ Settings")
        model = st.selectbox(
            "AI Model",
            options=["gpt-4o-mini", "gpt-4o"],
            index=0,
            help="gpt-4o-mini is faster and cheaper; gpt-4o is more capable"
        )
        st.session_state.selected_model = model

        st.divider()
        st.markdown("**📋 What I can help with:**")
        st.markdown("""
- 🔍 Search the book catalog
- 📖 Borrow a book
- ♻️ Return a book
- ⏳ Renew your loan
- 💡 Get book recommendations
- 📌 Place a hold on a book
        """)
        st.divider()
        st.caption("Late fee: $0.25/day | Loan period: 14 days | Max renewals: 2")

        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    # Initialize DB and session state
    get_db()
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "selected_model" not in st.session_state:
        st.session_state.selected_model = "gpt-4o-mini"

    # Welcome screen with quick-action buttons
    if len(st.session_state.messages) == 0:
        with st.chat_message("assistant"):
            st.markdown("Hello! 👋 I'm your library assistant. How can I help you today?")
            st.markdown("")
            cols = st.columns(3)
            quick_actions = [
                ("🔍 Search Catalog", "I want to search for a book"),
                ("📖 Borrow a Book", "I want to borrow a book"),
                ("♻️ Return a Book", "I want to return a book"),
                ("⏳ Renew a Loan", "I want to renew my book loan"),
                ("💡 Recommendations", "Can you recommend some books?"),
                ("📌 Place a Hold", "I want to place a hold on a book"),
            ]
            for i, (label, prompt) in enumerate(quick_actions):
                if cols[i % 3].button(label, use_container_width=True):
                    st.session_state.messages.append({"role": "user", "content": prompt})
                    st.rerun()

    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Process latest user message if unresponded
    if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    response = chat_with_tools(
                        st.session_state.messages,
                        st.session_state.selected_model
                    )
                except Exception as e:
                    response = f"⚠️ Something went wrong: {str(e)}. Please check your API key and try again."
            st.markdown(response)
        st.session_state.messages.append({"role": "assistant", "content": response})
        st.rerun()

    # Chat input
    if prompt := st.chat_input("Ask about books, borrowing, returns, renewals, holds, or recommendations..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.rerun()


if __name__ == "__main__":
    main()
