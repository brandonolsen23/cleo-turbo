"""
Dependency injection for FastAPI routes.
"""

import re
from fastapi import Request, HTTPException, Depends
from ..database.connection import get_connection


def fts_query(q: str) -> str:
    """Sanitize a user search string for FTS5 MATCH with prefix support.

    Strips FTS5 operators and appends * to the last token so partial
    typing works (e.g. "248 M" matches "248 Manitoba Street").
    """
    # Remove FTS5 special operators and punctuation (keep alphanumeric, spaces, hyphens)
    cleaned = re.sub(r'[^\w\s\-]', ' ', q)
    tokens = cleaned.split()
    if not tokens:
        return '""'
    # Last token gets a prefix wildcard; others stay as-is
    return " ".join(tokens[:-1] + [tokens[-1] + "*"])


def get_db():
    """Yield a database connection for the duration of a request."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def get_current_user(request: Request):
    """Extract and validate the current user from the JWT token."""
    from .auth import decode_token
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = auth_header[7:]
    user = decode_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


def require_admin(user=Depends(get_current_user)):
    """Require the current user to be an admin."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin required")
    return user
