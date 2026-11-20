import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Step 1: Add project root to sys.path and load environment variables
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from typing import Optional, Dict, Any
from Backend.api.upload import router as upload_router
from Backend.api.conversations import router as conversations_router
from Backend.api.auth_middleware import get_current_user_optional, get_current_user_required
from Backend.services.supabase_service import get_supabase_client
from history_aware_generation import (
    create_session,
    ask_question,
    setup_rag,
    get_retriever,
    get_embeddings,
    get_model,
)

# Step 2: Lifespan to load AI models on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.getLogger("uvicorn.error").info("Loading RAG embeddings and Qdrant database (k=6)...")
    app.state.embeddings = get_embeddings()
    app.state.retriever = get_retriever(app.state.embeddings)
    app.state.model = get_model()
    yield

# Step 3: Create FastAPI application FIRST
app = FastAPI(
    title="RAG Application API",
    description="Document Upload and RAG Backend",
    version="1.0.0",
    lifespan=lifespan
)

# Step 4: Allow frontend to communicate (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Step 5: Register API routers
app.include_router(
    upload_router,
    prefix="/api",
    tags=["Documents"]
)
app.include_router(
    conversations_router,
    prefix="/api",
    tags=["Conversations"]
)

# Optional: Mount Frontend static directory for direct browsing
from fastapi.staticfiles import StaticFiles
frontend_dir = ROOT / "Frontend"
if frontend_dir.exists():
    app.mount("/Frontend", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

# Step 6: Define question structure 
class ChatRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None

# Step 7: Endpoints
@app.get("/")
def home():
    try:
        from Backend.services.qdrant_service import get_qdrant_client, QDRANT_COLLECTION
        client = get_qdrant_client()
        count = client.count(collection_name=QDRANT_COLLECTION).count
        return {
            "message": "RAG Backend is running",
            "status": "active",
            "database": "Qdrant Cloud",
            "collection": QDRANT_COLLECTION,
            "total_chunks": count,
            "connected": True
        }
    except Exception as e:
        import os
        return {
            "message": "RAG Backend is running",
            "status": "active",
            "database": "Qdrant Cloud",
            "collection": os.getenv("QDRANT_COLLECTION", "rag_documents_v2"),
            "connected": False,
            "error": str(e)
        }

@app.get("/api/auth/config")
def auth_config():
    """Provides public Supabase configuration for frontend client initialization."""
    import os
    return {
        "supabase_url": os.getenv("SUPABASE_URL", ""),
        "supabase_anon_key": os.getenv("SUPABASE_ANON_KEY", "") or os.getenv("SUPABASE_KEY", "")
    }

class SignUpRequest(BaseModel):
    email: str
    password: str

@app.post("/api/auth/signup")
def signup_endpoint(payload: SignUpRequest):
    """
    Registers a new user in Supabase Auth.
    When Email Confirmation is disabled, creates user with email_confirm=True,
    bypassing Supabase's rate-limited free-tier SMTP mailer and immediately returning an authentic session.
    """
    import os
    from supabase import create_client as make_client

    email = payload.email.strip().lower()
    password = payload.password

    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="A valid email address is required.")
    if not password or len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long.")

    admin_client = get_supabase_client()
    if not admin_client:
        raise HTTPException(status_code=500, detail="Database authentication service is not configured.")

    # 1. Create user in Supabase Auth with email pre-confirmed
    try:
        user_res = admin_client.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True
        })
    except Exception as e:
        err_msg = str(e)
        err_lower = err_msg.lower()
        if (
            "already registered" in err_lower
            or "already been registered" in err_lower
            or "already exists" in err_lower
            or "user_already_exists" in err_lower
        ):
            raise HTTPException(
                status_code=409,
                detail="An account with this email address already exists. Please sign in instead."
            )
        if "rate limit" in err_lower or "429" in err_msg:
            raise HTTPException(
                status_code=429,
                detail="Signup rate limit reached. Please wait a moment before trying again."
            )
        if "password" in err_lower:
            raise HTTPException(
                status_code=400,
                detail="Password must be at least 8 characters and meet security requirements."
            )
        raise HTTPException(status_code=400, detail=f"Registration failed: {err_msg}")

    # 2. Sync profile into public.users
    try:
        admin_client.table("users").upsert({
            "id": str(user_res.user.id),
            "email": email,
            "role": "member"
        }).execute()
    except Exception:
        pass

    # 3. Acquire authentic Supabase JWT session via sign_in_with_password
    try:
        anon_key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY")
        anon_client = make_client(os.getenv("SUPABASE_URL"), anon_key)
        login_res = anon_client.auth.sign_in_with_password({
            "email": email,
            "password": password
        })

        return {
            "success": True,
            "user": {
                "id": str(user_res.user.id),
                "email": user_res.user.email,
                "role": getattr(user_res.user, "role", "authenticated")
            },
            "session": {
                "access_token": login_res.session.access_token,
                "refresh_token": login_res.session.refresh_token,
                "expires_at": login_res.session.expires_at
            }
        }
    except Exception as login_err:
        # User created successfully, return user info even if instant login needs manual sign in
        return {
            "success": True,
            "user": {
                "id": str(user_res.user.id),
                "email": user_res.user.email,
                "role": getattr(user_res.user, "role", "authenticated")
            },
            "session": None,
            "message": "Account created successfully. Please sign in with your credentials."
        }

class ResetPasswordRequest(BaseModel):
    email: str

@app.post("/api/auth/reset-password")
def reset_password(payload: ResetPasswordRequest):
    """Sends password reset link via Supabase Auth without leaking user existence."""
    email = payload.email.strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="A valid email address is required.")
    client = get_supabase_client()
    if client:
        try:
            client.auth.reset_password_for_email(email)
        except Exception:
            pass
    return {
        "success": True,
        "message": "If an account exists with this email address, password reset instructions have been sent."
    }

@app.post("/session")
def new_session():
    return {"session_id": create_session()}

@app.post("/chat")
def chat(
    request: ChatRequest,
    user: Dict[str, Any] = Depends(get_current_user_required)
):
    if not request.question.strip():
        raise HTTPException(
            status_code=400,
            detail="Question cannot be empty"
        )
    try:
        # Dynamically fetch fresh retriever using pre-warmed embeddings (~3ms).
        # Searches across the full Qdrant Cloud shared knowledge base so all shared documents are accessible.
        embeddings = getattr(app.state, "embeddings", None) or get_embeddings()
        retriever = get_retriever(embeddings, session_id=None)
        model = getattr(app.state, "model", None) or get_model()

        active_sid = request.session_id or request.conversation_id or "default"
        conv_id = request.conversation_id or request.session_id

        return ask_question(
            request.question,
            active_sid,
            retriever,
            model,
            user_id=user.get("id"),
            conversation_id=conv_id
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(error)}")

@app.get("/debug_qdrant")
@app.get("/debug_chroma")
def debug_vectorstore():
    from Backend.services.qdrant_service import get_qdrant_client, QDRANT_COLLECTION
    try:
        client = get_qdrant_client()
        col_info = client.get_collection(QDRANT_COLLECTION)
        count = client.count(QDRANT_COLLECTION).count
        points, _ = client.scroll(QDRANT_COLLECTION, limit=100, with_payload=True, with_vectors=False)
        sources = list(set(
            p.payload.get("metadata", {}).get("source", p.payload.get("metadata", {}).get("filename"))
            for p in points if p.payload
        ))
        return {
            "status": "connected",
            "backend": "qdrant_cloud",
            "collection": QDRANT_COLLECTION,
            "total_vectors": count,
            "points_count": col_info.points_count,
            "indexed_sources_sample": sources
        }
    except Exception as e:
        return {
            "status": "error",
            "backend": "qdrant_cloud",
            "detail": str(e)
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "Backend.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )