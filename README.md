# 📚 Library Management Chatbot

An AI-powered conversational chatbot for managing a public library system — built with **Streamlit**, **OpenAI function calling**, and **ChromaDB**.

Instead of traditional forms and dropdowns, members interact in plain English: *"I want to borrow Dune"*, *"Can I renew my copy of 1984?"*, *"What sci-fi books do you have available?"*

---

## ✨ Features (6 Use Cases)

| # | Feature | Description |
|---|---------|-------------|
| 1 | **Borrow Book** | Check out a book with member ID; enforces availability and sets 14-day due date |
| 2 | **Search Catalog** | Find books by title, author, genre, or filter to available-only |
| 3 | **Return Book** | Process returns with automatic late fee calculation ($0.25/day) |
| 4 | **Renew Loan** | Extend due date by 14 days (max 2 renewals per book) |
| 5 | **Book Recommendations** ⭐ | Genre-based or history-based recommendations personalized to the member |
| 6 | **Place a Hold** ⭐ | Join a waitlist queue for currently borrowed books, with queue position and estimated availability |

*⭐ = custom-designed use cases*

---

## 🏗️ Architecture

```
User (Natural Language)
        ↓
   Streamlit UI
        ↓
  OpenAI API (gpt-4o-mini / gpt-4o)
  [Function Calling — selects & calls the right tool]
        ↓
  Python Functions (borrow, return, renew, search, recommend, hold)
        ↓
  ChromaDB (PersistentClient)
  [Stores all loan records, holds, and catalog data]
        ↓
  Response generated and displayed in chat
```

---

## 🤖 Model Comparison

Two OpenAI models are available via a sidebar toggle. Here's how they compared across 5 test scenarios:

| Test Scenario | Model | Function Called ✓/✗ | Parameters Extracted ✓/✗ | Response Quality (1–5) |
|---|---|---|---|---|
| Simple borrow request (all info provided) | gpt-4o-mini | ✓ | ✓ | 5 |
| Simple borrow request | gpt-4o | ✓ | ✓ | 5 |
| Missing member ID (clarification needed) | gpt-4o-mini | ✓ | ✗ (asked for it) | 4 |
| Missing member ID | gpt-4o | ✓ | ✗ (asked for it) | 5 |
| Ambiguous query ("something sci-fi for next week") | gpt-4o-mini | ✓ | ✓ | 4 |
| Ambiguous query | gpt-4o | ✓ | ✓ | 5 |
| Custom use case — book recommendation by history | gpt-4o-mini | ✓ | ✓ | 4 |
| Custom use case — book recommendation | gpt-4o | ✓ | ✓ | 5 |
| Edge case — borrowing an already-checked-out book | gpt-4o-mini | ✓ | ✓ | 4 |
| Edge case | gpt-4o | ✓ | ✓ | 5 |

**Recommendation:** `gpt-4o-mini` handles all use cases correctly and is ~10x cheaper. For a real deployment, `gpt-4o-mini` is the practical choice unless response nuance on edge cases is critical.

---

## 🗄️ ChromaDB Schema

All records stored in a single `library_books` collection:

```python
# Loan record
{
  "id": "bk::{member_id}::{book_title}::{borrow_date}",
  "metadata": {
    "member_id": "M001",
    "book_title": "Dune",
    "author": "Frank Herbert",
    "genre": "Science Fiction",
    "isbn": "978-0441013593",
    "borrow_date": "2025-10-05",
    "due_date": "2025-10-19",
    "status": "borrowed",        # borrowed | returned | on_hold
    "renewals": "1",
    "late_fee": "0.0"
  }
}

# Hold record
{
  "id": "hold::{member_id}::{book_title}",
  "metadata": {
    "member_id": "M005",
    "book_title": "Dune",
    "status": "on_hold",
    "queue_position": "1",
    "estimated_available": "2025-10-19"
  }
}
```

Multi-field queries use the `$and` operator:
```python
db.get(where={"$and": [
    {"book_title": {"$eq": "Dune"}},
    {"status": {"$eq": "borrowed"}}
]})
```

---

## 🚀 Running Locally

### 1. Clone and install
```bash
git clone https://github.com/yourusername/library-chatbot.git
cd library-chatbot
pip install -r requirements.txt
```

### 2. Set your OpenAI API key
Create a `.streamlit/secrets.toml` file:
```toml
OPENAI_API_KEY = "sk-..."
```

Or set as an environment variable:
```bash
export OPENAI_API_KEY="sk-..."
```

### 3. Run
```bash
streamlit run app.py
```

---

## 🔑 Switching Models

Use the **sidebar dropdown** in the app to toggle between `gpt-4o-mini` (default, faster/cheaper) and `gpt-4o` (more capable). The same 6 functions are used for both — the only change is the model string passed to the OpenAI API.

---

## 🛠️ Tech Stack

- **[Streamlit](https://streamlit.io)** — conversational web UI
- **[OpenAI API](https://platform.openai.com)** — natural language understanding via function calling
- **[ChromaDB](https://www.trychroma.com)** — persistent vector database for loan records
- **Python 3.10+**

---

## 📁 Project Structure

```
library-chatbot/
├── app.py              # Main application (UI + functions + OpenAI integration)
├── requirements.txt    # Python dependencies
└── README.md           # This file
```

---

*Built as part of MIS491 — extended and redeployed as a portfolio project.*
