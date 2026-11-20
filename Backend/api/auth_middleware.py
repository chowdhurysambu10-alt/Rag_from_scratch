import logging
from typing import Optional, Dict, Any
from fastapi import Request, Header, HTTPException, status
from Backend.services.supabase_service import verify_supabase_jwt, is_supabase_configured

logger = logging.getLogger("uvicorn.error")


def get_current_user_required(
    request: Request,
    authorization: Optional[str] = None
) -> Dict[str, Any]:
    """
    Enforces that a valid, cryptographically verified Supabase JWT is provided.
    Raises HTTP 401 Unauthorized if missing, expired, or invalid.
    NEVER trusts user_id or X-User-ID from the client.
    """
    token = authorization if isinstance(authorization, str) else request.headers.get("Authorization")
    if not token or not isinstance(token, str) or not token.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please sign in.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    user = verify_supabase_jwt(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return user


def get_current_user_optional(
    request: Request,
    authorization: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Extracts the user from Supabase JWT if present and valid.
    Returns None if token is absent or invalid.
    NEVER trusts X-User-ID without a verified JWT.
    """
    token = authorization if isinstance(authorization, str) else request.headers.get("Authorization")
    if token and isinstance(token, str) and token.startswith("Bearer "):
        return verify_supabase_jwt(token)
    return None
