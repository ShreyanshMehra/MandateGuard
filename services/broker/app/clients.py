import httpx

from .config import BROKER_SERVICE_TOKEN, MOCK_BANK_URL, OPA_URL


class OpaUnavailableError(Exception):
    pass


class MockBankUnavailableError(Exception):
    pass


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
