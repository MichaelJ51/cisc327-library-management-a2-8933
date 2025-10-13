# tests/conftest.py
import os
import pytest
import sqlite3
import database  # your module

@pytest.fixture(scope="session", autouse=True)
def create_test_db(tmp_path_factory):
    """
    Create a persistent temp SQLite file for the whole test session
    and initialize schema using database.init_database().
    """
    db_dir = tmp_path_factory.mktemp("db")
    test_db_path = db_dir / "test.db"

    # Point the app to the test database file
    database.DATABASE = str(test_db_path)

    # Create tables
    database.init_database()

    # (Optional) prove it exists
    assert os.path.exists(test_db_path)

@pytest.fixture(autouse=True)
def clean_tables():
    """
    Before each test, start from a clean DB state.
    """
    conn = database.get_db_connection()
    with conn:
        conn.execute("DELETE FROM borrow_records;")
        conn.execute("DELETE FROM books;")
    conn.close()
