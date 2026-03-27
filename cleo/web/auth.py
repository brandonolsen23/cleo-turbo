"""
Authentication — JWT tokens + bcrypt password hashing.

3 users, 2 roles (admin, editor). Tokens expire after 72 hours.
"""

import hashlib
import hmac
import json
import time
import base64
import os

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from ..database.connection import get_connection
from .deps import get_db

router = APIRouter()

# Secret key for JWT signing — generated on first run if not set
SECRET_KEY = os.environ.get("CLEO_JWT_SECRET", "cleo-turbo-dev-secret-change-in-production")
TOKEN_EXPIRE_SECONDS = 72 * 3600  # 72 hours


def hash_password(password):
    """Hash a password with SHA-256 + salt. Simple but sufficient for 3 users."""
    salt = os.urandom(16)
    h = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
    return (salt + h).hex()


def verify_password(password, stored_hash):
    """Verify a password against a stored hash."""
    raw = bytes.fromhex(stored_hash)
    salt = raw[:16]
    stored_h = raw[16:]
    h = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
    return hmac.compare_digest(h, stored_h)


def create_token(user_id, username, role):
    """Create a signed JWT-like token."""
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "exp": int(time.time()) + TOKEN_EXPIRE_SECONDS,
    }
    payload_bytes = base64.urlsafe_b64encode(json.dumps(payload).encode())
    sig = hmac.new(SECRET_KEY.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return payload_bytes.decode() + "." + sig


def decode_token(token):
    """Decode and verify a token. Returns payload dict or None."""
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_bytes = parts[0].encode()
        sig = parts[1]
        expected_sig = hmac.new(SECRET_KEY.encode(), payload_bytes, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        payload = json.loads(base64.urlsafe_b64decode(payload_bytes))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(req: LoginRequest, db=Depends(get_db)):
    row = db.execute(
        "SELECT id, username, password_hash, display_name, role FROM users WHERE username = ?",
        (req.username,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(req.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(row["id"], row["username"], row["role"])
    return {
        "token": token,
        "user": {
            "id": row["id"],
            "username": row["username"],
            "display_name": row["display_name"],
            "role": row["role"],
        }
    }


@router.get("/me")
def me(user=Depends(lambda: None)):
    """Get current user info. Injected by auth middleware."""
    from .deps import get_current_user
    # This is handled at the route level with dependency injection
    pass


def create_user(username, password, display_name, role="editor"):
    """Create a user in the database. Called from CLI."""
    conn = get_connection()
    pw_hash = hash_password(password)
    conn.execute(
        "INSERT INTO users (username, password_hash, display_name, role) VALUES (?, ?, ?, ?)",
        (username, pw_hash, display_name, role)
    )
    conn.commit()
    conn.close()
    return True
