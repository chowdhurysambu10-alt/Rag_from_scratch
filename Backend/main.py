import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Step 1: Locate existing RAG code and database directory
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Step 2: Import RAG functions
from history_aware_generation import (
    create_session,
    ask_question,
    setup_rag,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.getLogger("uvicorn.error").info("Loading RAG embeddings and database...")
    app.state.retriever, app.state.model = setup_rag()
    yield

# Step 3: Create FastAPI application
app = FastAPI(title="My RAG Chatbot", lifespan=lifespan)

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
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Step 5: Define question structure 
class ChatRequest(BaseModel):
    question: str
    session_id: str


# Step 6: Test API
@app.get("/")
def home():
    return {"message": "RAG Backend is running"}


# Step 7: Create a new conversation
@app.post("/session")
def new_session():
    return {
        "session_id": create_session()
    }
    
    
# Step 8: Ask the RAG chatbot
@app.post("/chat")
def chat(request: ChatRequest):
    if not request.question.strip():
        raise HTTPException(
            status_code=400,
            detail="Question cannot be empty"
        )

    try:
        result = ask_question(
            request.question,
            request.session_id,
            app.state.retriever,
            app.state.model
        )
        return result

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error)
        )
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred: {str(error)}"
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "Backend.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )
