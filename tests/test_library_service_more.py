import pytest
from datetime import datetime, timedelta

# Unit under test
from services.library_service import (
    add_book_to_catalog,
    borrow_book_by_patron,
    return_book_by_patron,
    calculate_late_fee_for_book,
    search_books_in_catalog,
    get_patron_status_report,
)

# ---------- R1: add_book_to_catalog ----------

def test_add_book_existing_path_returns_true(mocker):
    # cover the "existing = get_book_by_isbn(...); if existing: return True, ..." branch
    mocker.patch("services.library_service.get_book_by_isbn", return_value={"isbn": "1234567890123"})
    ok, msg = add_book_to_catalog("Clean Code", "Robert Martin", "1234567890123", 3)
    assert ok is True
    assert "successfully added" in msg.lower()

def test_add_book_insert_and_availability_success(mocker):
    mocker.patch("services.library_service.get_book_by_isbn", return_value=None)
    ins = mocker.patch("services.library_service.insert_book", return_value=True)
    ok, msg = add_book_to_catalog("Refactoring", "Martin Fowler", "1111111111111", 2)
    assert ok is True
    ins.assert_called_once()

def test_add_book_insert_fail(mocker):
    mocker.patch("services.library_service.get_book_by_isbn", return_value=None)
    mocker.patch("services.library_service.insert_book", return_value=False)
    ok, msg = add_book_to_catalog("X", "Y", "2222222222222", 1)
    assert ok is False and "database error" in msg.lower()

# ---------- R3: borrow_book_by_patron ----------

def test_borrow_book_not_available_branch(mocker):
    mocker.patch("services.library_service.get_book_by_id",
                 return_value={"title": "X", "available_copies": 0})
    ok, msg = borrow_book_by_patron("123456", 10)
    assert ok is False and "not available" in msg.lower()

def test_borrow_limit_reached_branch(mocker):
    mocker.patch("services.library_service.get_book_by_id",
                 return_value={"title": "X", "available_copies": 1})
    mocker.patch("services.library_service.get_patron_borrow_count", return_value=5)
    ok, msg = borrow_book_by_patron("123456", 10)
    assert ok is False and "maximum borrowing limit" in msg.lower()

def test_borrow_insert_record_fail_branch(mocker):
    mocker.patch("services.library_service.get_book_by_id",
                 return_value={"title": "X", "available_copies": 1})
    mocker.patch("services.library_service.get_patron_borrow_count", return_value=0)
    mocker.patch("services.library_service.insert_borrow_record", return_value=False)
    ok, msg = borrow_book_by_patron("123456", 10)
    assert ok is False and "creating borrow record" in msg.lower()

def test_borrow_update_availability_fail_branch(mocker):
    mocker.patch("services.library_service.get_book_by_id",
                 return_value={"title": "X", "available_copies": 1})
    mocker.patch("services.library_service.get_patron_borrow_count", return_value=0)
    mocker.patch("services.library_service.insert_borrow_record", return_value=True)
    mocker.patch("services.library_service.update_book_availability", return_value=False)
    ok, msg = borrow_book_by_patron("123456", 10)
    assert ok is False and "updating book availability" in msg.lower()

def test_borrow_success_happy_path(mocker):
    mocker.patch("services.library_service.get_book_by_id",
                 return_value={"title": "X", "available_copies": 1})
    mocker.patch("services.library_service.get_patron_borrow_count", return_value=0)
    mocker.patch("services.library_service.insert_borrow_record", return_value=True)
    mocker.patch("services.library_service.update_book_availability", return_value=True)
    ok, msg = borrow_book_by_patron("123456", 10)
    assert ok is True and "successfully borrowed" in msg.lower()

# ---------- R4: return_book_by_patron ----------

def test_return_no_active_record_branch(mocker):
    mocker.patch("services.library_service.get_book_by_id", return_value={"title": "X"})
    mocker.patch("services.library_service.update_borrow_record_return_date", return_value=False)
    ok, msg = return_book_by_patron("123456", 10)
    assert ok is False and "no active borrow" in msg.lower()

def test_return_update_book_not_found_on_second_fetch(mocker):
    # First fetch succeeds, second fetch after update fails
    mocker.patch("services.library_service.get_book_by_id",
                 side_effect=[{"title": "X"}, None])
    mocker.patch("services.library_service.update_borrow_record_return_date",
                 return_value={"due_date": (datetime.now() - timedelta(days=1)).isoformat()})
    ok, msg = return_book_by_patron("123456", 10)
    assert ok is False and "not found during update" in msg.lower()

def test_return_update_availability_error_branch(mocker):
    # Second fetch shows available < total, but update_book_availability fails
    mocker.patch("services.library_service.get_book_by_id",
                 side_effect=[{"title": "X"},
                              {"total_copies": 3, "available_copies": 2}])
    mocker.patch("services.library_service.update_borrow_record_return_date",
                 return_value={"due_date": (datetime.now() - timedelta(days=1)).isoformat()})
    mocker.patch("services.library_service.update_book_availability", return_value=False)
    ok, msg = return_book_by_patron("123456", 10)
    assert ok is False and "database error while updating book availability" in msg.lower()

def test_return_overdue_fee_path_success(mocker):
    past_due = (datetime.now() - timedelta(days=10)).isoformat()
    mocker.patch("services.library_service.get_book_by_id",
                 side_effect=[{"title": "X"},
                              {"total_copies": 3, "available_copies": 2}])
    mocker.patch("services.library_service.update_borrow_record_return_date",
                 return_value={"due_date": past_due})
    mocker.patch("services.library_service.update_book_availability", return_value=True)
    ok, msg = return_book_by_patron("123456", 10)
    assert ok is True and "late fee" in msg.lower()

def test_return_due_date_parse_exception_falls_back_to_no_fee(mocker):
    # Force the try/except block by giving a malformed due_date
    mocker.patch("services.library_service.get_book_by_id",
                 side_effect=[{"title": "X"},
                              {"total_copies": 2, "available_copies": 1}])
    mocker.patch("services.library_service.update_borrow_record_return_date",
                 return_value={"due_date": object()})  # not parseable -> triggers except: pass
    mocker.patch("services.library_service.update_book_availability", return_value=True)
    ok, msg = return_book_by_patron("123456", 10)
    assert ok is True and "no late fee" in msg.lower()

# ---------- R5: calculate_late_fee_for_book ----------

def test_calc_fee_not_returned_positive_fee(mocker):
    # active borrow with due date in the past (no return_date) -> "Not yet returned" path
    mocker.patch("services.library_service.get_book_by_id", return_value={"id": 1})
    row = {"due_date": (datetime.now() - timedelta(days=9)).isoformat()}  # 9 days overdue -> fee > 0
    mocker.patch("services.library_service.update_borrow_record_return_date", return_value=row)
    out = calculate_late_fee_for_book("123456", 10)
    assert out["fee_amount"] > 0
    assert out["status"].startswith("Not yet returned")

def test_calc_fee_returned_historical_fee(mocker):
    mocker.patch("services.library_service.get_book_by_id", return_value={"id": 1})
    row = {
        "due_date": (datetime.now() - timedelta(days=8)).isoformat(),
        "return_date": (datetime.now() - timedelta(days=1)).isoformat(),
    }
    mocker.patch("services.library_service.update_borrow_record_return_date", return_value=row)
    out = calculate_late_fee_for_book("123456", 10)
    assert out["fee_amount"] > 0
    assert out["status"].startswith("Returned")

# ---------- R6: search_books_in_catalog (hit branches quickly) ----------

def test_search_books_fallback_branch(mocker):
    books = [
        {"title": "Clean Code", "author": "Martin", "isbn": "1111111111111"},
        {"title": "Design Patterns", "author": "GoF", "isbn": "2222222222222"},
    ]
    mocker.patch("services.library_service.get_all_books", return_value=books)
    # unknown search_type -> fallback (title OR author)
    assert len(search_books_in_catalog("martin", "unknown")) == 1

# ---------- R7: get_patron_status_report ----------

def test_patron_status_with_overdue_fee_and_history(mocker):
    today = datetime.now().date()
    overdue = (today - timedelta(days=3)).isoformat()
    mocker.patch("services.library_service.get_patron_borrowed_books",
                 return_value=[{"book_id": 1, "title": "X", "due_date": overdue}])
    mocker.patch("services.library_service.get_patron_borrow_history",
                 return_value=[{"book_id": 1, "returned": True}])
    out = get_patron_status_report("123456")
    assert out["num_currently_borrowed"] == 1
    assert out["total_late_fees_owed"] > 0
    assert out["status"] == "Complete"
