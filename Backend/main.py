import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Step 1: Add project root to sys.path and load environment variables
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from Backend.api.upload import router as upload_router
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
    logging.getLogger("uvicorn.error").info("Loading RAG embeddings and database (k=6)...")
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

# Step 5: Register the Upload API router
app.include_router(
    upload_router,
    prefix="/api",
    tags=["Documents"]
)

# Optional: Mount Frontend static directory for direct browsing
from fastapi.staticfiles import StaticFiles
frontend_dir = ROOT / "Frontend"
if frontend_dir.exists():
    app.mount("/Frontend", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

# Step 6: Define question structure 
class ChatRequest(BaseModel):
    question: str
    session_id: str

# Step 7: Endpoints
@app.get("/")
def home():
    return {"message": "RAG Backend is running", "status": "active"}

@app.post("/session")
def new_session():
    return {"session_id": create_session()}

@app.post("/chat")
def chat(request: ChatRequest):
    if not request.question.strip():
        raise HTTPException(
            status_code=400,
            detail="Question cannot be empty"
        )
    try:
        # Dynamically fetch fresh retriever using pre-warmed embeddings with session isolation (~3ms).
        # Guarantees that newly uploaded files and deletions take effect immediately with full session scoping.
        embeddings = getattr(app.state, "embeddings", None)
        retriever = get_retriever(embeddings, session_id=request.session_id)

        return ask_question(
            request.question,
            request.session_id,
            retriever,
            app.state.model
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(error)}")

@app.get("/debug_chroma")
def debug_chroma():
    import chromadb
    client = chromadb.PersistentClient(path=str(ROOT / os.getenv("CHROMA_DIRECTORY", "db/chroma_local")))
    col = client.get_collection("rag_documents_v2")
    count = col.count()
    sources = col.get(include=["metadatas"])
    unique_sources = list(set(m.get("source") for m in sources["metadatas"] if m))
    
    r_count = app.state.retriever.vectorstore._collection.count() if hasattr(app.state, "retriever") else 0
    
    fresh_r = get_retriever(app.state.embeddings) if hasattr(app.state, "embeddings") else None
    fresh_count = fresh_r.vectorstore._collection.count() if fresh_r else 0
    fresh_sources = list(set(m.get("source") for m in fresh_r.vectorstore._collection.get(include=["metadatas"])["metadatas"] if m)) if fresh_r else []
    
    return {
        "client_count": count,
        "client_sources": unique_sources,
        "app_state_retriever_count": r_count,
        "fresh_retriever_count": fresh_count,
        "fresh_retriever_sources": fresh_sources
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "Backend.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )