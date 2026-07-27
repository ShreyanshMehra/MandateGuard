import os

DATABASE_URL = os.environ.get("DATABASE_URL", "")
OPA_URL = os.environ.get("OPA_URL", "http://opa:8181")
MOCK_BANK_URL = os.environ.get("MOCK_BANK_URL", "http://mock-bank:8000")
BROKER_SERVICE_TOKEN = os.environ.get("BROKER_SERVICE_TOKEN", "")
MAX_AGENT_TOKEN_TTL_SECONDS = int(os.environ.get("MAX_AGENT_TOKEN_TTL_SECONDS", "300"))
SUPPORTED_ACTION = "refund_payment"

BROKER_PERMIT_KEY_PATH = os.environ.get("BROKER_PERMIT_KEY_PATH", "")
BROKER_PERMIT_KEY_ID = os.environ.get("BROKER_PERMIT_KEY_ID", "")
BANK_RESULT_PUBLIC_KEY_B64 = os.environ.get("BANK_RESULT_PUBLIC_KEY_B64", "")
PERMIT_TTL_SECONDS = int(os.environ.get("PERMIT_TTL_SECONDS", "60"))
