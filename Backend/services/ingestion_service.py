import os
import logging
import time
from datetime import datetime, timezone
from uuid import uuid4, uuid5, NAMESPACE_DNS
from pathlib import Path
import hashlib
import tempfile
from dotenv import load_dotenv

from langchain_community.document_loaders import (
    TextLoader,
    PyPDFLoader,
    CSVLoader,
    Docx2txtLoader
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from qdrant_client import models

from Backend.services.qdrant_service import (
    get_qdrant_client,
    get_qdrant_vector_store,
    ensure_collection,
    QDRANT_COLLECTION,
    VECTOR_SIZE
)

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", QDRANT_COLLECTION)
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

logger = logging.getLogger("uvicorn.error")

_docs_cache = {
    "timestamp": 0.0,
    "data": None,
    "ttl": 15.0  # Cache for 15 seconds to ensure ultra-fast dashboard queries
}


def invalidate_docs_cache():
    """Invalidate documents cache upon upload or deletion."""
    _docs_cache["data"] = None
    _docs_cache["timestamp"] = 0.0


def handle_upload(
    content: bytes,
    original_filename: str,
    session_id: str,
    document_id: str = None,
    uploaded_by: str = "Shared Knowledge Base",
    uploader_id: str = None
):
    """
    Saves uploaded file bytes, extracts text, splits into chunks,
    prevents duplicate ingestion, and indexes into Qdrant Cloud and Supabase metadata.
    """
    if not document_id:
        document_id = str(uuid4())

    client = get_qdrant_client()
    ensure_collection(client, COLLECTION_NAME)

    # 1. Prevent duplicate document ingestion
    clean_name = Path(original_filename).name
    filter_dupe = models.Filter(
        should=[
            models.FieldCondition(key="metadata.filename", match=models.MatchValue(value=clean_name)),
            models.FieldCondition(key="metadata.source", match=models.MatchValue(value=clean_name)),
            models.FieldCondition(key="metadata.source", match=models.MatchValue(value=f"docs/{clean_name}"))
        ]
    )
    existing_count = client.count(collection_name=COLLECTION_NAME, count_filter=filter_dupe).count
    if existing_count > 0:
        raise ValueError(
            f"Document '{clean_name}' is already indexed in the shared Knowledge Base ({existing_count} chunks exist)."
        )

    ext = Path(original_filename).suffix.lower()

    # 2. Write uploaded bytes to a temporary file for loaders
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
        tmp_file.write(content)
        tmp_path = tmp_file.name

    try:
        # 3. Select loader based on file extension
        if ext == ".pdf":
            loader = PyPDFLoader(tmp_path)
        elif ext in [".txt", ".py", ".cpp", ".h", ".md", ".json"]:
            loader = TextLoader(tmp_path, encoding="utf-8", autodetect_encoding=True)
        elif ext == ".csv":
            loader = CSVLoader(tmp_path, autodetect_encoding=True)
        elif ext == ".docx":
            loader = Docx2txtLoader(tmp_path)
        else:
            raise ValueError(f"Unsupported file format: {ext}")

        raw_docs = loader.load()
        if not raw_docs:
            raise ValueError("No text could be extracted from this document.")

        num_pages = len(raw_docs)

        # 4. Split into overlapping chunks
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=700,
            chunk_overlap=120,
            separators=["\n\n", "\n", " ", ""]
        )
        chunks = text_splitter.split_documents(raw_docs)
        if not chunks:
            raise ValueError("Document yielded 0 chunks.")

        upload_time_iso = datetime.now(timezone.utc).isoformat()

        # 5. Attach shared metadata to every chunk
        for doc in chunks:
            doc.metadata["source"] = original_filename
            doc.metadata["filename"] = original_filename
            doc.metadata["session_id"] = str(session_id)
            doc.metadata["document_id"] = str(document_id)
            doc.metadata["uploaded_by"] = uploaded_by
            doc.metadata["upload_date"] = upload_time_iso

        # 6. Create deterministic UUID point IDs for Qdrant to prevent duplicate indexing
        ids = [
            str(uuid5(NAMESPACE_DNS, f"{session_id}:{document_id}:{i}"))
            for i in range(len(chunks))
        ]

        # 7. Store in Qdrant Cloud using existing embedding model
        embedding_model = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME)
        vectorstore = get_qdrant_vector_store(embedding_model, collection_name=COLLECTION_NAME)
        vectorstore.add_documents(documents=chunks, ids=ids)

        invalidate_docs_cache()

        vectors_stored = len(ids)

        # 8. Synchronize document metadata with Supabase shared_documents table
        try:
            from Backend.services.supabase_service import register_shared_document
            register_shared_document(
                document_id=document_id,
                filename=original_filename,
                source=original_filename,
                chunks=len(chunks),
                pages=num_pages,
                uploaded_by=uploaded_by,
                uploader_id=uploader_id,
                file_size_bytes=len(content)
            )
        except Exception as e:
            logger.debug(f"Supabase document registration notice: {e}")

        # 9. Diagnostic Logging
        logger.info(
            f"[UPLOAD] session_id={session_id} | document_id={document_id} | filename={original_filename} | "
            f"uploaded_by={uploaded_by} | pages={num_pages} | chunks_created={len(chunks)} | "
            f"vectors_stored={vectors_stored} | collection={COLLECTION_NAME}"
        )

        return {
            "session_id": session_id,
            "document_id": document_id,
            "filename": original_filename,
            "uploaded_by": uploaded_by,
            "upload_date": upload_time_iso,
            "pages": num_pages,
            "chunks": len(chunks),
            "vectors_stored": vectors_stored,
            "collection_name": COLLECTION_NAME
        }
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def list_all_documents(force_refresh: bool = False):
    """Returns a list of all indexed documents in Qdrant with chunk counts, pages, and metadata."""
    now = time.time()
    if not force_refresh and _docs_cache["data"] is not None and (now - _docs_cache["timestamp"] < _docs_cache["ttl"]):
        return _docs_cache["data"]

    client = get_qdrant_client()
    ensure_collection(client, COLLECTION_NAME)

    summary = {}
    offset = None

    while True:
        points, offset = client.scroll(
            collection_name=COLLECTION_NAME,
            offset=offset,
            limit=1000,
            with_payload=["metadata"],
            with_vectors=False
        )

        for p in points:
            if not p.payload:
                continue
            meta = p.payload.get("metadata", {})
            source = meta.get("source") or meta.get("filename") or "Unknown"
            filename = Path(source).name
            uploaded_by = meta.get("uploaded_by") or "Shared Knowledge Base"
            upload_date = meta.get("upload_date") or meta.get("creationdate")

            if filename not in summary:
                summary[filename] = {
                    "filename": filename,
                    "source": source,
                    "chunks": 0,
                    "pages": set(),
                    "session_ids": set(),
                    "document_ids": set(),
                    "uploaded_by": uploaded_by,
                    "upload_date": upload_date,
                    "status": "Indexed"
                }

            summary[filename]["chunks"] += 1
            page = meta.get("page")
            if page is not None:
                summary[filename]["pages"].add(page)
            sid = meta.get("session_id")
            if sid:
                summary[filename]["session_ids"].add(sid)
            did = meta.get("document_id")
            if did:
                summary[filename]["document_ids"].add(did)

        if offset is None:
            break

    result = []
    for fname, data in summary.items():
        ext = Path(fname).suffix.lower().replace(".", "").upper() or "DOC"
        result.append({
            "filename": fname,
            "source": data["source"],
            "chunks": data["chunks"],
            "pages": len(data["pages"]) if data["pages"] else 1,
            "type": ext,
            "session_ids": list(data["session_ids"]),
            "document_ids": list(data["document_ids"]),
            "uploaded_by": data.get("uploaded_by", "Shared Knowledge Base"),
            "upload_date": data.get("upload_date"),
            "status": "Indexed"
        })

    sorted_result = sorted(result, key=lambda x: x["filename"].lower())
    _docs_cache["data"] = sorted_result
    _docs_cache["timestamp"] = now
    return sorted_result


def delete_document_by_name(filename: str):
    """Deletes all chunks associated with a source filename from Qdrant Cloud."""
    client = get_qdrant_client()
    ensure_collection(client, COLLECTION_NAME)

    clean_filename = Path(filename).name
    should_conditions = [
        models.FieldCondition(key="metadata.filename", match=models.MatchValue(value=clean_filename)),
        models.FieldCondition(key="metadata.source", match=models.MatchValue(value=clean_filename)),
        models.FieldCondition(key="metadata.source", match=models.MatchValue(value=f"docs/{clean_filename}")),
    ]
    if filename != clean_filename:
        should_conditions.append(
            models.FieldCondition(key="metadata.source", match=models.MatchValue(value=filename))
        )

    filter_condition = models.Filter(should=should_conditions)

    # Count matching points before deletion
    count_res = client.count(
        collection_name=COLLECTION_NAME,
        count_filter=filter_condition
    )

    if count_res.count == 0:
        raise ValueError(f"No indexed document found matching '{filename}'.")

    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=models.FilterSelector(filter=filter_condition)
    )

    invalidate_docs_cache()

    # Also synchronize deletion with Supabase shared_documents table
    try:
        from Backend.services.supabase_service import delete_shared_document_record
        delete_shared_document_record(clean_filename)
        delete_shared_document_record(filename)
    except Exception as e:
        logger.debug(f"Supabase document deletion sync: {e}")

    remaining_res = client.count(collection_name=COLLECTION_NAME)

    logger.info(f"[DELETE] Removed {count_res.count} chunks for file '{filename}' from collection '{COLLECTION_NAME}'")

    return {
        "success": True,
        "filename": filename,
        "deleted_chunks": count_res.count,
        "remaining_chunks": remaining_res.count
    }
