import pytest
from unittest.mock import Mock

# module under test
from services.library_services import pay_late_fees, refund_late_fee_payment
# for mock spec
from services.payment_service import PaymentGateway


# -------------------------
# pay_late_fees() tests
# -------------------------

def test_pay_late_fees_success(mocker):
    # STUB DB deps: calculate_late_fee_for_book + get_book_by_id
    mocker.patch(
        "services.library_services.calculate_late_fee_for_book",
        return_value={"fee_amount": 5.00, "days_overdue": 3, "status": "ok"},
    )
    mocker.patch(
        "services.library_services.get_book_by_id",
        return_value={"title": "Clean Code"},
    )

    # MOCK gateway
    gateway = Mock(spec=PaymentGateway)
    gateway.process_payment.return_value = (True, "txn_123", "Approved")

    ok, msg, txn = pay_late_fees("123456", 1, payment_gateway=gateway)

    assert ok is True and txn == "txn_123"
    gateway.process_payment.assert_called_once_with(
        patron_id="123456", amount=5.00, description="Late fees for 'Clean Code'"
    )


def test_pay_late_fees_declined_by_gateway(mocker):
    mocker.patch(
        "services.library_services.calculate_late_fee_for_book",
        return_value={"fee_amount": 7.50, "days_overdue": 6, "status": "ok"},
    )
    mocker.patch(
        "services.library_services.get_book_by_id",
        return_value={"title": "Refactoring"},
    )

    gateway = Mock(spec=PaymentGateway)
    gateway.process_payment.return_value = (False, "", "Payment declined")

    ok, msg, txn = pay_late_fees("123456", 42, payment_gateway=gateway)

    assert ok is False and txn is None
    assert "declined" in msg.lower()
    gateway.process_payment.assert_called_once_with(
        patron_id="123456", amount=7.50, description="Late fees for 'Refactoring'"
    )


def test_pay_late_fees_invalid_patron_id_gateway_not_called():
    gateway = Mock(spec=PaymentGateway)

    ok, msg, txn = pay_late_fees("12", 1, payment_gateway=gateway)

    assert ok is False and txn is None
    gateway.process_payment.assert_not_called()


def test_pay_late_fees_zero_fee_skips_gateway(mocker):
    mocker.patch(
        "services.library_services.calculate_late_fee_for_book",
        return_value={"fee_amount": 0.0, "days_overdue": 0, "status": "ok"},
    )
    # get_book_by_id should not be used when fee is zero, but stubbing is fine
    mocker.patch(
        "services.library_services.get_book_by_id",
        return_value={"title": "DDD"},
    )

    gateway = Mock(spec=PaymentGateway)

    ok, msg, txn = pay_late_fees("123456", 10, payment_gateway=gateway)

    assert ok is False and txn is None
    assert "no late fees" in msg.lower()
    gateway.process_payment.assert_not_called()


def test_pay_late_fees_network_error_exception_handled(mocker):
    mocker.patch(
        "services.library_services.calculate_late_fee_for_book",
        return_value={"fee_amount": 3.50, "days_overdue": 2, "status": "ok"},
    )
    mocker.patch(
        "services.library_services.get_book_by_id",
        return_value={"title": "Patterns of Enterprise Application Architecture"},
    )

    gateway = Mock(spec=PaymentGateway)
    gateway.process_payment.side_effect = Exception("network error")

    ok, msg, txn = pay_late_fees("123456", 2, payment_gateway=gateway)

    assert ok is False and txn is None
    assert "error" in msg.lower()
    gateway.process_payment.assert_called_once()  # tried once


# -------------------------
# refund_late_fee_payment() tests
# -------------------------

def test_refund_success():
    gateway = Mock(spec=PaymentGateway)
    gateway.refund_payment.return_value = (True, "Refund of $5.00 processed successfully.")

    ok, msg = refund_late_fee_payment("txn_abc_123", 5.00, payment_gateway=gateway)

    assert ok is True
    assert "refund" in msg.lower()
    gateway.refund_payment.assert_called_once_with("txn_abc_123", 5.00)


@pytest.mark.parametrize("bad_txn", ["", "abc", "pay_123"])
def test_refund_rejects_invalid_transaction_id_and_skips_gateway(bad_txn):
    gateway = Mock(spec=PaymentGateway)

    ok, msg = refund_late_fee_payment(bad_txn, 5.00, payment_gateway=gateway)

    assert ok is False
    assert "invalid transaction id" in msg.lower()
    gateway.refund_payment.assert_not_called()


@pytest.mark.parametrize("bad_amount", [0, -1.0, 15.01])
def test_refund_rejects_invalid_amounts_and_skips_gateway(bad_amount):
    gateway = Mock(spec=PaymentGateway)

    ok, msg = refund_late_fee_payment("txn_abc_123", bad_amount, payment_gateway=gateway)

    assert ok is False
    assert ("greater than 0" in msg.lower()) or ("exceeds" in msg.lower())
    gateway.refund_payment.assert_not_called()

from unittest.mock import Mock

# --- Extra coverage for pay_late_fees() ---

def test_pay_late_fees_missing_fee_amount_skips_gateway(mocker):
    # fee dict lacks 'fee_amount' key -> should bail early
    mocker.patch("services.library_services.calculate_late_fee_for_book",
                 return_value={"days_overdue": 3, "status": "ok"})
    mocker.patch("services.library_services.get_book_by_id",
                 return_value={"title": "Clean Code"})
    gateway = Mock(spec=PaymentGateway)

    ok, msg, txn = pay_late_fees("123456", 1, payment_gateway=gateway)

    assert ok is False and txn is None
    assert "unable to calculate" in msg.lower()
    gateway.process_payment.assert_not_called()


def test_pay_late_fees_book_not_found_skips_gateway(mocker):
    mocker.patch("services.library_services.calculate_late_fee_for_book",
                 return_value={"fee_amount": 4.0, "days_overdue": 2, "status": "ok"})
    mocker.patch("services.library_services.get_book_by_id", return_value=None)
    gateway = Mock(spec=PaymentGateway)

    ok, msg, txn = pay_late_fees("123456", 99, payment_gateway=gateway)

    assert ok is False and txn is None
    assert "book not found" in msg.lower()
    gateway.process_payment.assert_not_called()


def test_pay_late_fees_auto_instantiates_gateway_when_none(mocker):
    # Don’t pass a gateway -> function should create PaymentGateway()
    mocker.patch("services.library_services.calculate_late_fee_for_book",
                 return_value={"fee_amount": 5.0, "days_overdue": 2, "status": "ok"})
    mocker.patch("services.library_services.get_book_by_id",
                 return_value={"title": "Refactoring"})

    # Patch the class *in the module under test*
    MockGatewayClass = mocker.patch("services.library_services.PaymentGateway")
    instance = MockGatewayClass.return_value
    instance.process_payment.return_value = (True, "txn_X", "OK")

    ok, msg, txn = pay_late_fees("123456", 2)  # no gateway injected

    assert ok is True and txn == "txn_X"
    instance.process_payment.assert_called_once_with(
        patron_id="123456", amount=5.0, description="Late fees for 'Refactoring'"
    )

# --- Extra coverage for refund_late_fee_payment() ---

def test_refund_failed_message_and_verification():
    gateway = Mock(spec=PaymentGateway)
    gateway.refund_payment.return_value = (False, "Declined")

    ok, msg = refund_late_fee_payment("txn_abc_123", 5.0, payment_gateway=gateway)

    assert ok is False
    assert "failed" in msg.lower() or "declined" in msg.lower()
    gateway.refund_payment.assert_called_once_with("txn_abc_123", 5.0)


def test_refund_auto_instantiation_and_exception(mocker):
    # No gateway passed -> auto-instantiate; also cover the except path
    MockGatewayClass = mocker.patch("services.library_services.PaymentGateway")
    instance = MockGatewayClass.return_value
    instance.refund_payment.side_effect = Exception("network")

    ok, msg = refund_late_fee_payment("txn_abc_123", 5.0)  # no gateway

    assert ok is False
    assert "error" in msg.lower()
    instance.refund_payment.assert_called_once_with("txn_abc_123", 5.0)
