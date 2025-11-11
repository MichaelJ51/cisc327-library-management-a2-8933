import pytest
from services.payment_service import PaymentGateway


# Disable real sleeps to speed up tests
@pytest.fixture(autouse=True)
def _no_sleep(mocker):
    mocker.patch("services.payment_service.time.sleep", return_value=None)


# ---------- process_payment() tests ----------

def test_process_payment_invalid_amount_zero():
    gw = PaymentGateway()
    ok, txn, msg = gw.process_payment("123456", 0, "x")
    assert not ok
    assert txn == ""
    assert "invalid amount" in msg.lower()


def test_process_payment_amount_exceeds_limit():
    gw = PaymentGateway()
    ok, txn, msg = gw.process_payment("123456", 1000.01, "x")
    assert not ok
    assert txn == ""
    assert "exceeds limit" in msg.lower()


def test_process_payment_invalid_patron_length():
    gw = PaymentGateway()
    ok, txn, msg = gw.process_payment("12345", 10, "x")  # 5 digits
    assert not ok
    assert txn == ""
    assert "invalid patron id" in msg.lower()


def test_process_payment_success_deterministic_txn(mocker):
    mocker.patch("services.payment_service.time.time", return_value=1_700_000_000)
    gw = PaymentGateway()
    ok, txn, msg = gw.process_payment("123456", 10.5, "Late fees")
    assert ok
    assert txn == "txn_123456_1700000000"
    assert "processed successfully" in msg


# ---------- refund_payment() tests ----------

def test_refund_invalid_transaction_id_empty():
    gw = PaymentGateway()
    ok, msg = gw.refund_payment("", 5)
    assert not ok
    assert "invalid transaction id" in msg.lower()


@pytest.mark.parametrize("bad_txn", ["abc", "pay_123"])  # missing 'txn_' prefix
def test_refund_invalid_transaction_id_prefix(bad_txn):
    gw = PaymentGateway()
    ok, msg = gw.refund_payment(bad_txn, 5)
    assert not ok
    assert "invalid transaction id" in msg.lower()


def test_refund_invalid_amount_nonpositive():
    gw = PaymentGateway()
    ok, msg = gw.refund_payment("txn_abc_1", 0)
    assert not ok
    assert "invalid refund amount" in msg.lower()



# ---------- verify_payment_status() tests ----------

def test_verify_payment_status_not_found():
    gw = PaymentGateway()
    out = gw.verify_payment_status("bad_id")
    assert out["status"] == "not_found"
    assert "transaction not found" in out["message"].lower()


def test_verify_payment_status_completed_has_fields(mocker):
    mocker.patch("services.payment_service.time.time", return_value=1_700_000_002)
    gw = PaymentGateway()
    out = gw.verify_payment_status("txn_abc_1")
    assert out["transaction_id"] == "txn_abc_1"
    assert out["status"] == "completed"
    assert isinstance(out["amount"], float)
    assert out["timestamp"] == 1_700_000_002
