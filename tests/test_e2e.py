import pytest
from playwright.sync_api import Page, expect

BASE_URL = "http://localhost:5000"

TEST_ISBN = "9100123456789"     

@pytest.fixture(scope="session", autouse=True)
def headless_override(browser_type_launch_args):
    browser_type_launch_args["headless"] = True
    return browser_type_launch_args


def test_add_book_appears_in_catalog(page: Page):

    page.goto(f"{BASE_URL}/add_book")

    page.fill("input[name='title']", "E2E Testing Book")
    page.fill("input[name='author']", "Michael Jin")

    # ← THIS USES THE SHARED ISBN
    page.fill("input[name='isbn']", TEST_ISBN)

    page.fill("input[name='total_copies']", "5")
    page.click("button[type='submit']")

    page.goto(f"{BASE_URL}/catalog")

    book_row = page.locator("tr", has_text="E2E Testing Book").filter(
        has_text=TEST_ISBN
    )
    expect(book_row).to_be_visible()


def test_borrow_book_updates_availability(page: Page):

    # (Re)add same book because the DB persists)
    page.goto(f"{BASE_URL}/add_book")

    page.fill("input[name='title']", "E2E Testing Book")
    page.fill("input[name='author']", "Michael Jin")

    # ← SAME ISBN HERE TOO
    page.fill("input[name='isbn']", TEST_ISBN)

    page.fill("input[name='total_copies']", "5")
    page.click("button[type='submit']")

    page.goto(f"{BASE_URL}/catalog")

    book_row = page.locator("tr", has_text="E2E Testing Book").filter(
        has_text=TEST_ISBN
    )

    expect(book_row).to_be_visible()
    expect(book_row.get_by_text("5/5 Available")).to_be_visible()

    # Borrow the Book
    book_row.locator("input[name='patron_id']").fill("100001")
    book_row.locator("button[type='submit']").click()

    flash_success = page.locator(".flash-success")
    expect(flash_success).to_be_visible()
    expect(flash_success).to_contain_text("Successfully borrowed")

    expect(book_row.get_by_text("4/5 Available")).to_be_visible()
