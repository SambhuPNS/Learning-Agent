import os
import sys
from pathlib import Path

import pytest

os.environ["FIRESTORE_ENABLED"] = "false"
os.environ["GOOGLE_CLOUD_PROJECT"] = ""
os.environ["GOOGLE_CLIENT_ID"] = ""
os.environ["TEACHER_INVITE_CODE"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="session", autouse=True)
def isolated_store(tmp_path_factory):
    from app import store as store_module

    assert isinstance(store_module.store, store_module.LocalStore)
    store_module.STORE_PATH = tmp_path_factory.mktemp("store") / "store.json"
    store_module.store.data = store_module.JsonStore.migrate({})
