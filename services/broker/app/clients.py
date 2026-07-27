import httpx

from .config import BROKER_SERVICE_TOKEN, MOCK_BANK_URL, OPA_URL


class OpaUnavailableError(Exception):
    pass


class MockBankUnavailableError(Exception):
    pass


class BankExecutionOutcome:
    """Result of calling the mock bank's refund execution endpoint.

    status is one of SUCCEEDED, FAILED or UNKNOWN. UNKNOWN means the broker
    cannot determine whether the bank applied the refund (transport error,
    5xx, or a response whose signature failed verification) -- per
    docs/DATA_MODEL.md invariant 6, budgets must keep treating it as
    consuming capacity until reconciled, and it must never be retried
    blindly (invariant 10)."""

    def __init__(self, status: str, document: dict | None, signature_b64: str | None, key_id: str | None):
        self.status = status
        self.document = document
        self.signature_b64 = signature_b64
        self.key_id = key_id


def execute_bank_refund(*, request_id: str, payment_id: str, amount_minor: int, currency: str, permit_token: str) -> BankExecutionOutcome:
    try:
        response = httpx.post(
            f"{MOCK_BANK_URL}/internal/v1/refunds",
            headers={"X-Broker-Service-Token": BROKER_SERVICE_TOKEN, "X-Action-Permit": permit_token},
            json={
                "request_id": request_id,
                "payment_id": payment_id,
                "amount_minor": amount_minor,
                "currency": currency,
            },
            timeout=5.0,
        )
    except httpx.HTTPError:
        return BankExecutionOutcome("UNKNOWN", None, None, None)

    if response.status_code == 200:
        body = response.json()
        return BankExecutionOutcome("SUCCEEDED", body["document"], body["signature_b64"], body["key_id"])
    if response.status_code in (401, 404, 409, 422):
        return BankExecutionOutcome("FAILED", None, None, None)
    return BankExecutionOutcome("UNKNOWN", None, None, None)


def evaluate_refund_policy(input_doc: dict) -> dict:
    """Calls OPA outside of any database transaction (docs/DATA_MODEL.md
    "Transaction rule"). Raises OpaUnavailableError on any failure so the
    caller can fail closed per docs/THREAT_MODEL.md."""
    try:
        response = httpx.post(
            f"{OPA_URL}/v1/data/mandateguard/refund/decision",
            json={"input": input_doc},
            timeout=5.0,
        )
        response.raise_for_status()
        return response.json()["result"]
    except (httpx.HTTPError, KeyError) as exc:
        raise OpaUnavailableError(str(exc)) from exc


def fetch_trusted_payment(payment_id: str) -> dict | None:
    """Fetches trusted payment/customer context from the private mock bank.
    Returns None if the payment does not exist. Raises MockBankUnavailableError
    on any transport/auth failure so the caller can fail closed."""
    try:
        response = httpx.get(
            f"{MOCK_BANK_URL}/internal/v1/payments/{payment_id}",
            headers={"X-Broker-Service-Token": BROKER_SERVICE_TOKEN},
            timeout=5.0,
        )
    except httpx.HTTPError as exc:
        raise MockBankUnavailableError(str(exc)) from exc

    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise MockBankUnavailableError(f"unexpected status {response.status_code}")
    return response.json()
