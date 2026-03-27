"""
Dependency injection for FastAPI routes.
"""

from fastapi import Request, HTTPException, Depends
from ..database.connection import get_connection


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
