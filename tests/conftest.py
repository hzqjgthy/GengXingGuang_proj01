import os
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ["LLM_PROVIDER"] = "demo"
os.environ["LLM_API_KEY"] = "test-disabled"
os.environ["LLM_BASE_URL"] = ""
os.environ["LLM_MODEL"] = ""

from app import create_app  # noqa: E402


@pytest.fixture()
def app():
    test_db = PROJECT_ROOT / "data" / "pytest.db"
    if test_db.exists():
        test_db.unlink()
    application = create_app({"TESTING": True, "DB_ENGINE": "sqlite", "SQLITE_PATH": str(test_db)})
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def case_a(client):
    response = client.get("/api/cases/case-a")
    return response.get_json()["case"]
