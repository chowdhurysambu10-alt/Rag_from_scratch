from typing import Optional, Dict, Any
from uuid import uuid4
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request, Depends, status
from Backend.services.ingestion_service import (
    handle_upload,
    list_all_documents,
    delete_document_by_name
)
from Backend.services.qdrant_service import get_qdrant_client, QDRANT_COLLECTION
from Backend.api.auth_middleware import get_current_user_required
from history_aware_generation import get_retriever, create_session, get_session

router = APIRouter()

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


@router.post("/upload")
async def upload_pdf(
    request: Request,
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    user: Dict[str, Any] = Depends(get_current_user_required)
):
    """
    Upload a PDF to the global shared knowledge base.
    Requires an authenticated user session.
    """
    # 1. Validate filename
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename.")

    ext = file.filename.lower()
    if not ext.endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF documents are supported for this upload pipeline."
        )

    # 2. Read uploaded file
    content = await file.read()

    # 3. Validate size
    if not content:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is empty."
        )

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="Maximum file size is 20 MB."
        )

    # 4. Validate PDF signature
    if not content.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=400,
            detail="Invalid PDF file: Missing %PDF- header."
        )

    # Extract authenticated uploader information
    uploader_email = user.get("email") or "Authenticated User"
    uploader_id = user.get("id")

    try:
        # 5. Reuse active conversation session_id or initialize a new one if not provided
        if session_id and session_id.strip():
            clean_session_id = session_id.strip()
            get_session(clean_session_id)
        else:
            clean_session_id = create_session()

        document_id = str(uuid4())

        # 6. Call ingestion service with uploader metadata and duplicate prevention
        result = handle_upload(
            content=content,
            original_filename=file.filename,
            session_id=clean_session_id,
            document_id=document_id,
            uploaded_by=uploader_email,
            uploader_id=uploader_id
        )

        # 7. Refresh retriever immediately for global shared retrieval
        if hasattr(request.app.state, "embeddings") and request.app.state.embeddings:
            request.app.state.retriever = get_retriever(request.app.state.embeddings)

        return {
            "success": True,
            "message": "Document uploaded and indexed successfully into shared Knowledge Base.",
            **result
        }

    except ValueError as ve:
        err_msg = str(ve)
        if "already indexed" in err_msg.lower():
            raise HTTPException(status_code=409, detail=err_msg)
        raise HTTPException(status_code=400, detail=err_msg)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Document processing failed: {str(e)}"
        )

    finally:
        await file.close()


@router.get("/documents")
def get_documents(user: Dict[str, Any] = Depends(get_current_user_required)):
    """Retrieve all documents and collection statistics from Qdrant Cloud for authenticated users."""
    try:
        docs = list_all_documents()
        try:
            client = get_qdrant_client()
            total_chunks = client.count(collection_name=QDRANT_COLLECTION).count
        except Exception:
            total_chunks = sum(d["chunks"] for d in docs)

        return {
            "success": True,
            "total_documents": len(docs),
            "total_chunks": total_chunks,
            "collection": QDRANT_COLLECTION,
            "database": "Qdrant Cloud",
            "status": "connected",
            "documents": docs
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch documents: {str(e)}"
        )


@router.delete("/documents/{filename:path}")
def delete_document(
    request: Request,
    filename: str,
    user: Dict[str, Any] = Depends(get_current_user_required)
):
    """Delete all chunks for a document from Qdrant Cloud. Requires authenticated user."""
    try:
        result = delete_document_by_name(filename)
        # Refresh retriever immediately so deleted document is dropped from search
        if hasattr(request.app.state, "embeddings") and request.app.state.embeddings:
            request.app.state.retriever = get_retriever(request.app.state.embeddings)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete document: {str(e)}"
        )
