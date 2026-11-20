import os
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path
from dotenv import load_dotenv
import jwt
from jwt import PyJWKClient
from supabase import create_client, Client

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

logger = logging.getLogger("uvicorn.error")

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
# Prefer service role key for backend operations (bypasses RLS for admin sync), otherwise anon key
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")

_supabase_client: Optional[Client] = None
_jwks_client: Optional[PyJWKClient] = None


def is_supabase_configured() -> bool:
    """Check whether Supabase environment variables are provided."""
    return bool(SUPABASE_URL and SUPABASE_KEY and "your-project" not in SUPABASE_URL)


def get_supabase_client() -> Optional[Client]:
    """Returns a singleton Supabase admin client."""
    global _supabase_client
    if not is_supabase_configured():
        return None

    if _supabase_client is None:
        try:
            _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            logger.info(f"Supabase client initialized successfully for URL: {SUPABASE_URL[:25]}...")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            return None

    return _supabase_client


def get_jwks_client() -> Optional[PyJWKClient]:
    """Returns singleton PyJWKClient for asymmetric ES256/RS256 JWT verification."""
    global _jwks_client
    if not is_supabase_configured():
        return None
    if _jwks_client is None:
        try:
            jwks_url = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
            _jwks_client = PyJWKClient(jwks_url, cache_keys=True, max_cached_keys=10)
        except Exception as e:
            logger.error(f"Failed to initialize JWKS client: {e}")
            return None
    return _jwks_client


def verify_supabase_jwt(token: str) -> Optional[Dict[str, Any]]:
    """
    Cryptographically verifies a Supabase Bearer JWT access token.
    Enforces signature verification, expiration check, and authentic user identity.
    NEVER accepts unverified signatures or expired tokens.
    """
    if not token or not isinstance(token, str):
        return None

    clean_token = token.replace("Bearer ", "").strip()
    if not clean_token or clean_token.startswith("mock_"):
        return None

    # 1. Authoritative verification via Supabase Auth API
    client = get_supabase_client()
    if client:
        try:
            user_response = client.auth.get_user(clean_token)
            if user_response and user_response.user:
                u = user_response.user
                return {
                    "id": str(u.id),
                    "email": getattr(u, "email", "authenticated_user"),
                    "role": getattr(u, "role", "authenticated")
                }
        except Exception as e:
            # Token rejected by Supabase Auth server (e.g. invalid, expired, revoked)
            logger.debug(f"Supabase auth.get_user rejected token: {e}")

    # 2. Asymmetric ES256 verification using Supabase public JWKS
    jwks = get_jwks_client()
    if jwks:
        try:
            signing_key = jwks.get_signing_key_from_jwt(clean_token)
            payload = jwt.decode(
                clean_token,
                signing_key.key,
                algorithms=["ES256", "RS256"],
                audience="authenticated",
                options={"require": ["exp", "sub"]}
            )
            sub = payload.get("sub")
            if sub:
                return {
                    "id": str(sub),
                    "email": payload.get("email", "authenticated_user"),
                    "role": payload.get("role", "authenticated")
                }
        except Exception as e:
            logger.debug(f"JWKS asymmetric decode rejected token: {e}")

    # 3. Symmetric HS256 verification if a genuine JWT secret is configured
    if SUPABASE_JWT_SECRET and SUPABASE_JWT_SECRET != "your-jwt-secret":
        try:
            payload = jwt.decode(
                clean_token,
                SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
                options={"require": ["exp", "sub"]}
            )
            sub = payload.get("sub")
            if sub:
                return {
                    "id": str(sub),
                    "email": payload.get("email", "authenticated_user"),
                    "role": payload.get("role", "authenticated")
                }
        except Exception as e:
            logger.debug(f"HS256 secret decode rejected token: {e}")

    # All cryptographic verification attempts failed
    return None


# ----------------------------------------------------------------------------
# User Profile Operations (public.users)
# ----------------------------------------------------------------------------

def get_user_profile(user_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve user record from public.users table."""
    client = get_supabase_client()
    if not client:
        return None
    try:
        res = client.table("users").select("*").eq("id", user_id).execute()
        return res.data[0] if res.data else None
    except Exception:
        return None


def delete_user_account(user_id: str) -> bool:
    """
    Deletes a user from Supabase.
    Cascades automatically to delete public.users, conversations, and messages.
    """
    client = get_supabase_client()
    if not client:
        return False
    try:
        client.auth.admin.delete_user(user_id)
        return True
    except Exception as e:
        logger.error(f"Failed to delete user account {user_id}: {e}")
        return False


# ----------------------------------------------------------------------------
# Conversation Operations (Strict User & Conversation Isolation)
# ----------------------------------------------------------------------------

def create_conversation(user_id: str, title: str = "New Conversation") -> Dict[str, Any]:
    """Create a new conversation belonging to an authenticated user."""
    client = get_supabase_client()
    if not client:
        raise RuntimeError("Database connection not configured.")

    res = client.table("conversations").insert({
        "user_id": user_id,
        "title": title
    }).execute()

    if res.data and len(res.data) > 0:
        return res.data[0]
    raise ValueError("Failed to create conversation in database.")


def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve conversation metadata by ID."""
    client = get_supabase_client()
    if not client:
        return None

    res = client.table("conversations").select("*").eq("id", conversation_id).execute()
    if res.data and len(res.data) > 0:
        return res.data[0]
    return None


def verify_conversation_ownership(user_id: str, conversation_id: str) -> bool:
    """Check if the specified conversation exists and is owned by user_id."""
    conv = get_conversation(conversation_id)
    if not conv:
        return False
    return str(conv.get("user_id")) == str(user_id)


def get_user_conversations(user_id: str) -> List[Dict[str, Any]]:
    """Retrieve all conversations strictly belonging to the authenticated user."""
    client = get_supabase_client()
    if not client:
        return []

    res = client.table("conversations") \
        .select("*") \
        .eq("user_id", user_id) \
        .order("updated_at", desc=True) \
        .execute()

    return res.data or []


def rename_conversation(user_id: str, conversation_id: str, new_title: str) -> bool:
    """Rename a conversation only if owned by user_id."""
    if not verify_conversation_ownership(user_id, conversation_id):
        return False

    client = get_supabase_client()
    if not client:
        return False

    res = client.table("conversations") \
        .update({"title": new_title}) \
        .eq("id", conversation_id) \
        .eq("user_id", user_id) \
        .execute()

    return bool(res.data and len(res.data) > 0)


def delete_conversation(user_id: str, conversation_id: str) -> bool:
    """Delete a conversation only if owned by user_id."""
    if not verify_conversation_ownership(user_id, conversation_id):
        return False

    client = get_supabase_client()
    if not client:
        return False

    res = client.table("conversations") \
        .delete() \
        .eq("id", conversation_id) \
        .eq("user_id", user_id) \
        .execute()

    return bool(res.data and len(res.data) > 0)


# ----------------------------------------------------------------------------
# Message Operations (Strict User & Conversation Isolation)
# ----------------------------------------------------------------------------

def add_message(
    conversation_id: str,
    user_id: str,
    role: str,
    content: str,
    sources: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Save a user or assistant message to Supabase after verifying conversation ownership."""
    client = get_supabase_client()
    if not client:
        raise RuntimeError("Database connection not configured.")

    if not verify_conversation_ownership(user_id, conversation_id):
        raise PermissionError(f"User {user_id} does not own conversation {conversation_id}")

    res = client.table("messages").insert({
        "conversation_id": conversation_id,
        "user_id": user_id,
        "role": role,
        "content": content,
        "sources": sources or []
    }).execute()

    try:
        client.table("conversations").update({"updated_at": "now()"}).eq("id", conversation_id).execute()
    except Exception:
        pass

    return res.data[0] if res.data else {}


def get_conversation_messages(user_id: str, conversation_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve chronologically ordered messages only if owned by user_id."""
    if not verify_conversation_ownership(user_id, conversation_id):
        return []

    client = get_supabase_client()
    if not client:
        return []

    res = client.table("messages") \
        .select("*") \
        .eq("conversation_id", conversation_id) \
        .eq("user_id", user_id) \
        .order("created_at", desc=False) \
        .limit(limit) \
        .execute()

    return res.data or []


# ----------------------------------------------------------------------------
# Shared Documents Registry (Global Shared Knowledge Base)
# ----------------------------------------------------------------------------

def register_shared_document(
    document_id: str,
    filename: str,
    source: str,
    chunks: int,
    pages: int,
    uploaded_by: str,
    uploader_id: Optional[str] = None,
    file_size_bytes: int = 0
) -> Dict[str, Any]:
    """Register document metadata into Supabase shared_documents table."""
    client = get_supabase_client()
    if not client:
        return {
            "document_id": document_id,
            "filename": filename,
            "source": source,
            "chunks": chunks,
            "pages": pages,
            "uploaded_by": uploaded_by
        }

    data = {
        "document_id": document_id,
        "filename": filename,
        "source": source,
        "chunks": chunks,
        "pages": pages,
        "file_size_bytes": file_size_bytes,
        "uploaded_by": uploaded_by,
        "uploader_id": uploader_id,
        "status": "Indexed"
    }

    res = client.table("shared_documents").upsert(data, on_conflict="filename").execute()
    return res.data[0] if res.data else data


def get_shared_documents() -> List[Dict[str, Any]]:
    """Get all shared documents metadata from Supabase."""
    client = get_supabase_client()
    if not client:
        return []

    res = client.table("shared_documents") \
        .select("*") \
        .order("upload_date", desc=True) \
        .execute()

    return res.data or []


def delete_shared_document_record(filename: str) -> bool:
    """Remove a document record from Supabase shared_documents."""
    client = get_supabase_client()
    if not client:
        return True

    res = client.table("shared_documents").delete().eq("filename", filename).execute()
    return bool(res.data and len(res.data) > 0)
