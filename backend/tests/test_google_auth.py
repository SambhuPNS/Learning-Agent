"""Google sign-in, using real ID-token verification against a locally generated signing key."""

import json
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient
from google.auth import crypt, jwt
from google.auth.transport import requests as google_requests

from app import auth, main
from app import store as store_module
from app.store import LocalStore

CLIENT_ID = "test-client.apps.googleusercontent.com"
client = TestClient(main.app)


def _key_pair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(1).not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=1))
            .sign(key, hashes.SHA256()))
    private_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption())
    return crypt.RSASigner.from_string(private_pem, key_id="test-key"), cert.public_bytes(serialization.Encoding.PEM).decode()


SIGNER, CERT = _key_pair()
FORGER, _ = _key_pair()


class FakeCertsEndpoint:
    status = 200

    def __call__(self, url, method="GET", **kwargs):
        return SimpleNamespace(status=self.status, data=json.dumps({"test-key": CERT}).encode())


@pytest.fixture(autouse=True)
def google_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(store_module, "STORE_PATH", tmp_path / "store.json")
    monkeypatch.setattr(auth, "store", LocalStore())
    monkeypatch.setattr(auth, "GOOGLE_CLIENT_ID", CLIENT_ID)
    monkeypatch.setattr(main, "GOOGLE_CLIENT_ID", CLIENT_ID)
    monkeypatch.setattr(google_requests, "Request", FakeCertsEndpoint)


def credential(signer=SIGNER, **claims) -> str:
    now = int(time.time())
    payload = {"iss": "https://accounts.google.com", "aud": CLIENT_ID, "sub": "google-ana", "email": "ana@gmail.com",
               "email_verified": True, "name": "Ana Silva", "iat": now, "exp": now + 600, **claims}
    return jwt.encode(signer, payload).decode()


def sign_in(token: str, **body):
    return client.post("/api/auth/google", json={"credential": token, **body})


def test_first_google_sign_in_creates_account_and_later_ones_reuse_it():
    assert client.get("/api/health").json()["googleClientId"] == CLIENT_ID
    first = sign_in(credential())
    assert first.status_code == 200, first.text
    user = first.json()["user"]
    assert (user["name"], user["email"], user["role"]) == ("Ana Silva", "ana@gmail.com", "student")

    again = sign_in(credential(), role="teacher")
    assert again.json()["user"]["id"] == user["id"] and again.json()["user"]["role"] == "student"
    me = client.get("/api/me", headers={"Authorization": f"Bearer {again.json()['token']}"})
    assert me.json()["id"] == user["id"]

    password = {"name": "Pat", "email": "pat@example.com", "password": "secret123"}
    assert client.post("/api/auth/signup", json=password).status_code == 403
    assert client.post("/api/auth/login", json=password).status_code == 403


def test_invalid_google_credentials_are_rejected(monkeypatch):
    now = int(time.time())
    for token in (
        credential(aud="another-client.apps.googleusercontent.com"),
        credential(iss="https://evil.example.com"),
        credential(iat=now - 7200, exp=now - 3600),
        credential(signer=FORGER),
        credential(email_verified=False),
        "not-a-token",
    ):
        assert sign_in(token).status_code == 401
    assert not auth.store.all_users()

    monkeypatch.setattr(FakeCertsEndpoint, "status", 500)
    assert sign_in(credential()).status_code == 503


def test_teacher_invite_and_existing_accounts(monkeypatch):
    monkeypatch.setattr(auth, "TEACHER_INVITE_CODE", "school-42")
    teacher = credential(sub="google-teacher", email="teacher@school.org")
    assert sign_in(teacher, role="teacher", inviteCode="nope").status_code == 403
    assert sign_in(teacher, role="teacher", inviteCode="school-42").json()["user"]["role"] == "teacher"
    assert sign_in(teacher).json()["user"]["role"] == "teacher"
    assert sign_in(credential(sub="someone-else", email="teacher@school.org")).status_code == 401

    monkeypatch.setattr(auth, "GOOGLE_CLIENT_ID", "")
    legacy = client.post("/api/auth/signup", json={"name": "Leo", "email": "leo@gmail.com", "password": "secret123"})
    monkeypatch.setattr(auth, "GOOGLE_CLIENT_ID", CLIENT_ID)
    assert sign_in(credential(sub="google-leo", email="leo@gmail.com")).json()["user"]["id"] == legacy.json()["user"]["id"]
