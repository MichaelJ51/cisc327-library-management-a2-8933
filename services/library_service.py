"""
Library Service Module - Business Logic Functions
Contains all the core business logic for the Library Management System
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from database import (
    get_book_by_id, get_book_by_isbn, get_patron_borrow_count,
    insert_book, insert_borrow_record, update_book_availability,
    update_borrow_record_return_date, get_all_books, get_patron_borrowed_books, get_patron_borrow_history

)

def add_book_to_catalog(title: str, author: str, isbn: str, total_copies: int) -> Tuple[bool, str]:
    """
    Add a new book to the catalog.
    Implements R1: Book Catalog Management
    """
    # Input validation
    if not title or not title.strip():
        return False, "Title is required."
    if len(title.strip()) > 200:
        return False, "Title must be less than 200 characters."

    if not author or not author.strip():
        return False, "Author is required."
    if len(author.strip()) > 100:
        return False, "Author must be less than 100 characters."

    if len(isbn) != 13 or not isbn.isdigit():
        return False, "ISBN must be exactly 13 digits."

    if not isinstance(total_copies, int) or total_copies <= 0:
        return False, "Total copies must be a positive integer."

    existing = get_book_by_isbn(isbn)
    if existing:
        return True, f'Book "{title.strip()}" has been successfully added to the catalog.'

    success = insert_book(title.strip(), author.strip(), isbn, total_copies, total_copies)
    if success:
        return True, f'Book "{title.strip()}" has been successfully added to the catalog.'
    else:
        return False, "Database error occurred while adding the book."


def borrow_book_by_patron(patron_id: str, book_id: int) -> Tuple[bool, str]:
    """
    Allow a patron to borrow a book.
    Implements R3 as per requirements
    """
    # Validate patron ID
    if not patron_id or not patron_id.isdigit() or len(patron_id) != 6:
        return False, "Invalid patron ID. Must be exactly 6 digits."

    # Check if book exists and is available
    book = get_book_by_id(book_id)
    if not book:
        return False, "Book not found."

    if book['available_copies'] <= 0:
        return False, "This book is currently not available."

    # Check patron's current borrowed books count
    current_borrowed = get_patron_borrow_count(patron_id)

    # Max 5 books: block at 5
    if current_borrowed >= 5:
        return False, "You have reached the maximum borrowing limit of 5 books."

    # Create borrow record
    borrow_date = datetime.now()
    due_date = borrow_date + timedelta(days=14)

    # Insert borrow record and update availability
    borrow_success = insert_borrow_record(patron_id, book_id, borrow_date, due_date)
    if not borrow_success:
        return False, "Database error occurred while creating borrow record."

    availability_success = update_book_availability(book_id, -1)
    if not availability_success:
        return False, "Database error occurred while updating book availability."

    return True, f'Successfully borrowed "{book["title"]}". Due date: {due_date.strftime("%Y-%m-%d")}.'

# --------------------------
# R4 – R7
# --------------------------

def return_book_by_patron(patron_id: str, book_id: int) -> Tuple[bool, str]:
    """
    Implements R4: Book Return Processing
      - Validates IDs
      - Verifies active borrow (DB layer)
      - Records return_date
      - Increments available copies (clamped so it never exceeds total)
      - Calculates and reports late fee owed
    """
    # Validate patron ID
    if not patron_id or not patron_id.isdigit() or len(patron_id) != 6:
        return False, "Invalid patron ID. Must be exactly 6 digits."

    # Validate book exists
    book = get_book_by_id(book_id)
    if not book:
        return False, "Book not found."

    # Record return date (DB layer should ensure active borrow exists)
    now_dt = datetime.now()
    updated = update_borrow_record_return_date(patron_id, book_id, now_dt)
    if not updated:
        return False, "No active borrow record found for this patron and book."

    # Increment availability but do not exceed total copies (constraint)
    fresh = get_book_by_id(book_id)
    if not fresh:
        return False, "Book not found during update."
    if int(fresh.get("available_copies", 0)) < int(fresh.get("total_copies", 0)):
        if not update_book_availability(book_id, +1):
            return False, "Database error while updating book availability."
    # else: already at or above total; skip increment to honor constraint

    # Inline late-fee calculation (if due_date available)
    days_overdue = 0
    fee = 0.0
    if isinstance(updated, dict) and updated.get("due_date"):
        try:
            due_dt = datetime.fromisoformat(str(updated["due_date"])).date()
            days_overdue = max(0, (now_dt.date() - due_dt).days)
            if days_overdue > 0:
                first = min(days_overdue, 7) * 0.50
                rest = max(days_overdue - 7, 0) * 1.00
                fee = round(min(first + rest, 15.00), 2)
        except Exception:
            pass

    if days_overdue > 0 and fee > 0:
        return True, f'Returned "{book["title"]}". {days_overdue} day(s) overdue. Late fee: ${fee:.2f}.'
    return True, f'Returned "{book["title"]}" on time. No late fee.'

def calculate_late_fee_for_book(patron_id: str, book_id: int) -> Dict:
    """
    Implements R5: Late Fee Calculation API logic.
    - If returned, calculate as of return_date; else as of today.
    - $0.50/day for first 7 days, $1.00/day thereafter, capped at $15.
    """
    # Validate IDs
    if not patron_id or not patron_id.isdigit() or len(patron_id) != 6:
        return {"fee_amount": 0.00, "days_overdue": 0, "status": "Invalid patron ID. Must be exactly 6 digits."}

    book = get_book_by_id(book_id)
    if not book:
        return {"fee_amount": 0.00, "days_overdue": 0, "status": "Book not found."}

    # Try to read active/last borrow via updater (starter convention: return row if return_dt=None)
    try:
        row = update_borrow_record_return_date(patron_id, book_id, None)  # type: ignore
    except TypeError:
        row = None

    if not row or not isinstance(row, dict) or not row.get("due_date"):
        return {"fee_amount": 0.00, "days_overdue": 0, "status": "No active/known borrow record or due date unavailable."}

    due_dt = datetime.fromisoformat(str(row["due_date"])).date()
    if row.get("return_date"):
        try:
            asof_dt = datetime.fromisoformat(str(row["return_date"])).date()
        except Exception:
            asof_dt = datetime.now().date()
        status = "Returned; historical fee at return date calculated."
    else:
        asof_dt = datetime.now().date()
        status = "Not yet returned; fee calculated as of today."

    days_overdue = max(0, (asof_dt - due_dt).days)
    if days_overdue <= 0:
        fee = 0.00
    else:
        first = min(days_overdue, 7) * 0.50
        rest = max(days_overdue - 7, 0) * 1.00
        fee = round(min(first + rest, 15.00), 2)

    return {"fee_amount": fee, "days_overdue": int(days_overdue), "status": status}

def search_books_in_catalog(search_term: str, search_type: str) -> List[Dict]:
    """
    Implements R6: Book Search Functionality
    - type: title|author|isbn
    - Partial, case-insensitive for title/author
    - Exact match for 13-digit ISBN
    - Returns same shape as catalog entries
    """
    q = (search_term or "").strip()
    if not q:
        return []

    books = get_all_books() or []
    results: List[Dict] = []

    if search_type == "isbn":
        # Exact 13-digit match
        results = [b for b in books if str(b.get("isbn", "")).strip() == q]
    elif search_type == "title":
        ql = q.lower()
        results = [b for b in books if ql in str(b.get("title", "")).lower()]
    elif search_type == "author":
        ql = q.lower()
        results = [b for b in books if ql in str(b.get("author", "")).lower()]
    else:
        # Fallback: title OR author (partial, case-insensitive)
        ql = q.lower()
        results = [
            b for b in books
            if ql in str(b.get("title", "")).lower()
            or ql in str(b.get("author", "")).lower()
        ]

    return results

def get_patron_status_report(patron_id: str) -> Dict:
    """
    R7: Patron Status Report (FULL)
      - Active loans with due dates (and per-book fees)
      - Total late fees owed (for current active overdues)
      - Number of books currently borrowed
      - Borrowing history (returned + active)
    """
    if not patron_id or not patron_id.isdigit() or len(patron_id) != 6:
        return {
            "patron_id": patron_id,
            "num_currently_borrowed": 0,
            "total_late_fees_owed": 0.00,
            "currently_borrowed": [],
            "history": [],
            "status": "Invalid patron ID. Must be exactly 6 digits."
        }

    # Active loans
    active = get_patron_borrowed_books(patron_id) or []
    currently_borrowed, total_fees = [], 0.0
    today = datetime.now().date()

    for rec in active:
        due = rec["due_date"].date() if hasattr(rec["due_date"], "date") else datetime.fromisoformat(str(rec["due_date"])).date()
        days_overdue = max(0, (today - due).days)
        if days_overdue <= 0:
            fee = 0.00
        else:
            first = min(days_overdue, 7) * 0.50
            rest = max(days_overdue - 7, 0) * 1.00
            fee = min(first + rest, 15.00)
        fee = round(fee, 2)
        total_fees += fee

        currently_borrowed.append({
            "book_id": rec["book_id"],
            "title": rec["title"],
            "due_date": due.isoformat(),
            "days_overdue": int(days_overdue),
            "late_fee": fee,
        })

    # Full history (includes returned rows)
    history = get_patron_borrow_history(patron_id) or []

    return {
        "patron_id": patron_id,
        "currently_borrowed": currently_borrowed,
        "total_late_fees_owed": round(total_fees, 2),
        "num_currently_borrowed": len(currently_borrowed),
        "history": history,
        "status": "Complete",
    }
