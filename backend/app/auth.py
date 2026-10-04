import hashlib
import hmac
import secrets
import uuid

from fastapi import Depends, Header, HTTPException

from .config import TEACHER_INVITE_CODE
from .store import now_iso, store

PBKDF2_ITERATIONS = 200_000


def _hash_password(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS).hex()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _find_user_by_email(email: str) -> dict | None:
    return next((u for u in store.data["users"].values() if u["email"] == email), None)


def public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user.get("role", "student"),
        "profile": user.get("profile"),
        "progress": user.get("progress", {}),
    }


def _issue_token(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    store.data["tokens"][_hash_token(token)] = user_id
    return token


def signup(name: str, email: str, password: str, role: str = "student", invite_code: str = "") -> tuple[str, dict]:
    email = email.strip().lower()
    if role == "teacher" and TEACHER_INVITE_CODE and not hmac.compare_digest(invite_code.strip(), TEACHER_INVITE_CODE):
        raise HTTPException(403, "The teacher invite code is not correct.")
    with store.lock:
        if _find_user_by_email(email):
            raise HTTPException(409, "An account with this email already exists.")
        salt = secrets.token_bytes(16)
        user = {
            "id": uuid.uuid4().hex,
            "name": name.strip(),
            "email": email,
            "role": role,
            "salt": salt.hex(),
            "passwordHash": _hash_password(password, salt),
            "createdAt": now_iso(),
            "profile": None,
            "progress": {},
        }
        store.data["users"][user["id"]] = user
        token = _issue_token(user["id"])
        store.save()
    return token, user


def login(email: str, password: str) -> tuple[str, dict]:
    email = email.strip().lower()
    with store.lock:
        user = _find_user_by_email(email)
        if not user:
            raise HTTPException(401, "Incorrect email or password.")
        expected = _hash_password(password, bytes.fromhex(user["salt"]))
        if not hmac.compare_digest(expected, user["passwordHash"]):
            raise HTTPException(401, "Incorrect email or password.")
        token = _issue_token(user["id"])
        store.save()
    return token, user


def logout(token: str) -> None:
    with store.lock:
        store.data["tokens"].pop(_hash_token(token), None)
        store.save()


def _token_from_header(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Please sign in.")
    return authorization[7:].strip()


def current_user(authorization: str | None = Header(default=None)) -> dict:
    token = _token_from_header(authorization)
    user_id = store.data["tokens"].get(_hash_token(token))
    user = store.data["users"].get(user_id) if user_id else None
    if not user:
        raise HTTPException(401, "Your session has expired. Please sign in again.")
    return user


def current_token(authorization: str | None = Header(default=None)) -> str:
    return _token_from_header(authorization)


def current_student(user: dict = Depends(current_user)) -> dict:
    if user.get("role", "student") != "student":
        raise HTTPException(403, "This area is for student accounts.")
    return user


def current_teacher(user: dict = Depends(current_user)) -> dict:
    if user.get("role") != "teacher":
        raise HTTPException(403, "This area is for teacher accounts.")
    return user
