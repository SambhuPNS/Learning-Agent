import hashlib

import pytest
from google.cloud.firestore_v1 import _helpers

from scripts.migrate_store_to_firestore import document_batches, load_documents


def test_tokens_are_firestore_documents():
    documents = load_documents({
        "tokens": {"token-hash": "user-1"},
        "users": {"user-1": {"id": "user-1", "email": "student@example.com"}},
    })
    assert ("tokens", "token-hash", {"userId": "user-1"}) in documents
    email_id = hashlib.sha256(b"student@example.com").hexdigest()
    assert ("userEmails", email_id, {"userId": "user-1"}) in documents
    for _, _, payload in documents:
        _helpers.encode_dict(payload)


@pytest.mark.parametrize("data", [
    {"tokens": {"hash": None}},
    {"tokens": {"hash": ""}},
    {"users": {"user-1": "not a document"}},
    {"events": [{"ts": "missing-id"}]},
])
def test_invalid_imports_fail_before_writing(data):
    with pytest.raises(ValueError):
        load_documents(data)


def test_batches_stay_below_firestore_limit():
    documents = [("events", str(index), {"id": str(index)}) for index in range(901)]
    assert [len(batch) for batch in document_batches(documents)] == [450, 450, 1]
