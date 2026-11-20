import os
import time
from pathlib import Path
from threading import RLock
from uuid import uuid4

from dotenv import load_dotenv
from qdrant_client import models
from Backend.services.qdrant_service import get_qdrant_vector_store, QDRANT_COLLECTION

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_huggingface import HuggingFaceEmbeddings

from langchain_groq import ChatGroq

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

# Keep these settings aligned with your ingestion pipeline.


COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "rag_documents_v2")
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)
LLM_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
if not LLM_MODEL or "llama" in LLM_MODEL.lower():
    LLM_MODEL = "openai/gpt-oss-20b"
MAX_HISTORY_TURNS = 6
MAX_HISTORY_MESSAGES = MAX_HISTORY_TURNS * 2
SESSION_TTL = 30 * 60  # Seconds of inactivity

# Single-process development store; use Redis/DB for multi-worker deployment.
session_store = {}
store_lock = RLock()


def extract_text(content):
    """Extract text from Gemini/LangChain response content blocks."""
    if isinstance(content,str):
        
        return content
    
    if isinstance(content,list):
        return "".join(
            
            item if isinstance(item, str) else item.get("text", "")
            for item in content
            
            if isinstance(item, str)
            
            or (isinstance(item, dict) and item.get("type") == "text")
        )
    return str(content) if content is not None else ""


def create_session():
    session_id = str(uuid4())
    with store_lock:
        now = time.monotonic()
        for sid, entry in list(session_store.items()):
            if now - entry["last_active"] > SESSION_TTL:
                del session_store[sid]
        session_store[session_id] = {
            "history": [],
            "last_active": now,
            "lock": RLock(),
        }
    print(f"Session created: {session_id}")
    return session_id


def get_session(session_id):
    with store_lock:
        session = session_store.get(session_id)
        if session is None:
            # Auto-revive or register session if the server was restarted
            now = time.monotonic()
            session = {
                "history": [],
                "last_active": now,
                "lock": RLock(),
            }
            session_store[session_id] = session
            return session
        if time.monotonic() - session["last_active"] > SESSION_TTL:
            # Refresh expired session gracefully
            session["history"] = []
            session["last_active"] = time.monotonic()
            return session
        return session


def source_details(doc, index):
    """Make a citation entry from the loader's metadata."""
    metadata = doc.metadata or {}
    source = str(metadata.get("source") or "Unknown")
    filename = Path(source).name
    page = metadata.get("page")
    slide = metadata.get("slide")
    row = metadata.get("row")

    # PyPDFLoader is zero-based; our PPTX loader saves 1-based slide numbers.
    is_pdf = Path(source).suffix.lower() == ".pdf"
    page_number = page + 1 if is_pdf and isinstance(page, int) else None
    if slide is not None:
        location = f"Slide {slide}"
    elif page_number is not None:
        location = f"Page {page_number}"
    elif row is not None:
        location = f"CSV row {row}"
    else:
        location = "Location unavailable"

    return {
        "reference": f"[{index}]",
        "file": filename,
        "source": source,
        "page": page_number,
        "slide": slide,
        "row": row,
        "location": location,
    }


def get_embeddings():
    """Load or return the shared HuggingFace embedding model."""
    return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)


def get_retriever(embeddings=None, session_id=None):
    """Create a fresh retriever against the Qdrant Cloud collection.
    
    Using pre-cached embeddings, ensures newly uploaded documents are immediately searchable.
    When session_id is provided, applies metadata filtering for session scoping.
    When session_id is None, searches across the entire knowledge base.
    """
    if embeddings is None:
        embeddings = get_embeddings()

    store = get_qdrant_vector_store(embeddings, collection_name=COLLECTION_NAME)

    search_kwargs = {"k": 6}
    if session_id:
        search_kwargs["filter"] = models.Filter(
            must=[
                models.FieldCondition(
                    key="metadata.session_id",
                    match=models.MatchValue(value=str(session_id))
                )
            ]
        )
    return store.as_retriever(search_kwargs=search_kwargs)


def get_model():
    """Initialize the configured Groq LLM model with fallbacks."""
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        raise ValueError("GROQ_API_KEY is not set. Please provide it in your .env file or environment.")
    chosen_model = os.getenv("GROQ_MODEL", LLM_MODEL)
    if not chosen_model or "llama" in chosen_model.lower():
        chosen_model = "openai/gpt-oss-20b"
    return ChatGroq(
        model=chosen_model,
        api_key=groq_api_key,
        temperature=0.5,
        max_tokens=2048
    )


def setup_rag():
    """Initialize embeddings, retriever, and model for server startup."""
    embeddings = get_embeddings()
    retriever = get_retriever(embeddings)
    model = get_model()
    return retriever, model


def ask_question(user_question, session_id, retriever, model, user_id=None, conversation_id=None):
    """Rewrite the question, retrieve documents from shared knowledge base, stream answer, and save history."""
    if not user_question.strip():
        raise ValueError("Question cannot be empty")

    actual_conv_id = conversation_id or session_id
    session = get_session(session_id)
    with session["lock"]:
        if time.monotonic() - session["last_active"] > SESSION_TTL:
            raise ValueError("Session expired")
        session["last_active"] = time.monotonic()
        chat_history = list(session["history"][-MAX_HISTORY_MESSAGES:])

        # If Supabase is configured and conversation_id + user_id provided, sync user's private history
        if actual_conv_id and user_id:
            try:
                from Backend.services.supabase_service import get_conversation_messages, is_supabase_configured
                if is_supabase_configured():
                    db_msgs = get_conversation_messages(user_id=user_id, conversation_id=actual_conv_id, limit=MAX_HISTORY_MESSAGES)
                    if db_msgs:
                        supa_history = []
                        for m in db_msgs:
                            if m.get("role") == "user":
                                supa_history.append(HumanMessage(content=m.get("content", "")))
                            elif m.get("role") == "assistant":
                                supa_history.append(AIMessage(content=m.get("content", "")))
                        if supa_history:
                            chat_history = supa_history
            except Exception as e:
                print(f"Supabase history sync notice: {e}")

        print(f"\n--- You asked: {user_question} ---")

        # Step 1: Rewrite follow-up questions for retrieval.
        if chat_history:
            rewrite_messages = [
                SystemMessage(content=(
                    "You are a search-query rewriter. Given the conversation so far, "
                    "rewrite the user's latest message into ONE clear, self-contained "
                    "search query that captures the full intent (resolve pronouns, "
                    "references, and implied context). Output ONLY the rewritten query — "
                    "no explanation, no preamble."
                )),
                *chat_history,
                HumanMessage(content=f"Latest message: {user_question}"),
            ]
            rewrite_result = model.invoke(rewrite_messages)
            search_question = extract_text(rewrite_result.content).strip() or user_question
        else:
            search_question = user_question

        print(f"Searching for: {search_question}")

        # Step 2: Retrieve related document chunks.
        docs = retriever.invoke(search_question)
        print(f"Found {len(docs)} relevant documents")

        # Step 2b: Diagnostic logging for every chat request
        active_filter = getattr(retriever, "search_kwargs", {}).get("filter", {})
        retrieved_details = [
            f"{d.metadata.get('source', d.metadata.get('filename', 'Unknown'))} (Page {d.metadata.get('page', '?')})"
            for d in docs
        ]
        import logging
        logging.getLogger("uvicorn.error").info(
            f"[CHAT] session_id={session_id} | collection={COLLECTION_NAME} | "
            f"active_metadata_filter={active_filter} | retrieved_chunks={len(docs)} | "
            f"retrieved_files_pages={retrieved_details}"
        )

        # Step 3: Add metadata to the context and keep citations for the UI.
        sources = []
        context_parts = []
        for index, doc in enumerate(docs, start=1):
            info = source_details(doc, index)
            sources.append(info)
            context_parts.append(
                f"{info['reference']}\n"
                f"File: {info['file']}\n"
                f"Location: {info['location']}\n"
                f"Content:\n{doc.page_content}"
            )
            print(f"Doc {index}: {info['file']} | {info['location']}")
        context = "\n\n".join(context_parts) or "No documents retrieved."

        # Step 4: Final answer — natural, conversational, grounded.
        answer_messages = [
            SystemMessage(content=(
                "You are RAG AI, a friendly and knowledgeable document assistant. "
                "You help users explore and understand their uploaded documents.\n\n"
                "PERSONALITY & TONE:\n"
                "- Be warm, conversational, and approachable — like a smart colleague.\n"
                "- Use natural language. Avoid sounding robotic or formulaic.\n"
                "- Vary your sentence structure. Don't start every sentence the same way.\n"
                "- When appropriate, use brief transitions like \"Interestingly,\" "
                "\"It's worth noting that,\" or \"Based on what I found,\" to keep the "
                "flow natural.\n"
                "- For casual greetings (hi, hello, hey), respond warmly and briefly. "
                "Mention that you're ready to help with their documents.\n\n"
                "ANSWERING RULES:\n"
                "- Base ALL factual claims strictly on the Retrieved Documents below.\n"
                "- Synthesize information across chunks — don't just list what each chunk says.\n"
                "- Cite sources naturally using [1], [2], etc. Place citations at the end of "
                "the relevant sentence or paragraph, not after every single phrase.\n"
                "- Never invent or fabricate citations. Only cite documents actually provided.\n"
                "- If the documents don't contain the answer, say so honestly and naturally — "
                "e.g., \"I couldn't find that information in your uploaded documents.\"\n"
                "- Use the conversation history to understand context and pronouns, but don't "
                "treat previous chat messages as factual evidence.\n\n"
                "FORMATTING:\n"
                "- Use markdown for readability: **bold** for key terms, bullet points for "
                "lists, headings for long answers.\n"
                "- Keep answers concise but complete. Don't pad with unnecessary filler.\n"
                "- For short factual questions, give a direct answer first, then supporting detail.\n"
                "- Avoid repeating the same information from different chunks.\n"
                "- Never start your response with \"Based on the retrieved documents\" or "
                "\"According to the provided documents\" — just answer naturally."
            )),
            *chat_history,
            HumanMessage(content=(
                f"{user_question}\n\n"
                f"---\nRetrieved Documents:\n{context}"
            )),
        ]

        # Step 5: Stream once; also collect the full answer for memory and API output.
        print("\nAnswer:\n")
        answer_parts = []
        for chunk in model.stream(answer_messages):
            piece = extract_text(chunk.content)
            if piece:
                print(piece, end="", flush=True)
                answer_parts.append(piece)
        print()
        answer = "".join(answer_parts).strip()
        if not answer:
            raise RuntimeError("The model returned an empty answer")

        # Step 6: Save and keep only the latest six question/answer turns in memory.
        session["history"].extend([
            HumanMessage(content=user_question),
            AIMessage(content=answer),
        ])
        session["history"] = session["history"][-MAX_HISTORY_MESSAGES:]
        session["last_active"] = time.monotonic()

        # Step 6b: Persist to Supabase if conversation_id and user_id are active
        if actual_conv_id and user_id:
            try:
                from Backend.services.supabase_service import add_message, is_supabase_configured
                if is_supabase_configured():
                    add_message(conversation_id=actual_conv_id, user_id=user_id, role="user", content=user_question)
                    add_message(conversation_id=actual_conv_id, user_id=user_id, role="assistant", content=answer, sources=sources)
            except Exception as e:
                print(f"Supabase message persist notice: {e}")

        print(f"Memory: {len(session['history']) // 2} turns stored")

        print("\nRetrieved sources (not necessarily all cited):")
        for item in sources:
            print(f"{item['reference']} {item['file']} | {item['location']}")

        return {
            "answer": answer,
            "sources": sources,
            "session_id": session_id,
            "conversation_id": actual_conv_id
        }


def start_chat():
    retriever, model = setup_rag()
    session_id = create_session()
    print("\nRAG Chatbot Started! Type 'quit' to exit.")
    while True:
        try:
            question = input("\nYour question: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        if question.lower() == "quit":
            print("Goodbye!")
            break
        if not question:
            continue
        try:
            ask_question(question, session_id, retriever, model)
        except ValueError as exc:
            print(f"Session error: {exc}")
            session_id = create_session()
            print("New session created. Please ask your question again.")
        except Exception as exc:
            print(f"Error: {exc}")

if __name__ == "__main__":
    start_chat()
