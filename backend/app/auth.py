import hashlib
import hmac
import logging
import secrets
import uuid

from fastapi import Depends, Header, HTTPException
from google.auth import exceptions as google_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from .config import GOOGLE_CLIENT_ID, TEACHER_INVITE_CODE
from .store import now_iso, store

PBKDF2_ITERATIONS = 200_000
log = logging.getLogger("tutor.auth")


def _hash_password(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS).hex()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _find_user_by_email(email: str) -> dict | None:
    return store.find_user_by_email(email)


def public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user.get("role", "student"),
        "profile": user.get("profile"),
        "progress": user.get("progress", {}),
    }


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _check_invite(role: str, invite_code: str) -> None:
    if role == "teacher" and TEACHER_INVITE_CODE and not hmac.compare_digest(invite_code.strip(), TEACHER_INVITE_CODE):
        raise HTTPException(403, "The teacher invite code is not correct.")


def signup(name: str, email: str, password: str, role: str = "student", invite_code: str = "") -> tuple[str, dict]:
    email = email.strip().lower()
    _check_invite(role, invite_code)
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
    token = _new_token()
    if not store.create_user(user, _hash_token(token)):
        raise HTTPException(409, "An account with this email already exists.")
    return token, user


def login(email: str, password: str) -> tuple[str, dict]:
    email = email.strip().lower()
    user = _find_user_by_email(email)
    if not user or "passwordHash" not in user:
        raise HTTPException(401, "Incorrect email or password.")
    expected = _hash_password(password, bytes.fromhex(user["salt"]))
    if not hmac.compare_digest(expected, user["passwordHash"]):
        raise HTTPException(401, "Incorrect email or password.")
    token = _new_token()
    store.save_token(_hash_token(token), user["id"])
    return token, user


def _verify_google_credential(credential: str) -> dict:
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(503, "Google sign-in is not configured.")
    try:
        claims = google_id_token.verify_oauth2_token(
            credential, google_requests.Request(), GOOGLE_CLIENT_ID, clock_skew_in_seconds=10,
        )
    except google_exceptions.TransportError as exc:
        log.warning("Could not fetch Google sign-in certificates: %s", exc)
        raise HTTPException(503, "Could not reach Google to check your sign-in. Please try again.") from exc
    except (ValueError, google_exceptions.GoogleAuthError) as exc:
        log.warning("Rejected Google credential: %s", exc)
        raise HTTPException(401, "Google sign-in failed. Please try again.") from exc
    if not claims.get("sub") or not claims.get("email") or claims.get("email_verified") not in (True, "true"):
        raise HTTPException(401, "Your Google account needs a verified email address.")
    return claims


def google_sign_in(credential: str, role: str = "student", invite_code: str = "") -> tuple[str, dict]:
    claims = _verify_google_credential(credential)
    email = claims["email"].strip().lower()
    token = _new_token()
    user = _find_user_by_email(email)
    if user is None:
        _check_invite(role, invite_code)
        user = {
            "id": uuid.uuid4().hex,
            "name": str(claims.get("name") or "").strip()[:60] or email.split("@")[0][:60],
            "email": email,
            "role": role,
            "googleId": claims["sub"],
            "createdAt": now_iso(),
            "profile": None,
            "progress": {},
        }
        if not store.create_user(user, _hash_token(token)):
            raise HTTPException(409, "Your account was just created. Please sign in again.")
        return token, user
    # Accounts created before Google sign-in have no googleId and are matched by verified email.
    if user.get("googleId", claims["sub"]) != claims["sub"]:
        raise HTTPException(401, "This email is linked to a different Google account.")
    if "googleId" not in user:
        # Anyone could have registered this email with a password, so the verified owner's sign-in removes it.
        store.link_google_account(user["id"], claims["sub"])
    store.save_token(_hash_token(token), user["id"])
    return token, user


def logout(token: str) -> None:
    store.delete_token(_hash_token(token))


def _token_from_header(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Please sign in.")
    return authorization[7:].strip()


def current_user(authorization: str | None = Header(default=None)) -> dict:
    token = _token_from_header(authorization)
    user_id = store.get_token_user_id(_hash_token(token))
    user = store.get_user(user_id) if user_id else None
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
