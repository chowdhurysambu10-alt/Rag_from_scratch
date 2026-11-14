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
)

# Step 2: Lifespan to load AI models on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.getLogger("uvicorn.error").info("Loading RAG embeddings and database (k=6)...")
    app.state.retriever, app.state.model = setup_rag()
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
    allow_origins=[
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:5500",
        "http://localhost:5500"
    ],
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
        return ask_question(
            request.question,
            request.session_id,
            app.state.retriever,
            app.state.model
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(error)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "Backend.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )