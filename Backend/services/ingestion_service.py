import os
import logging
from uuid import uuid4
from pathlib import Path
import hashlib
import tempfile
import chromadb
from dotenv import load_dotenv

from langchain_community.document_loaders import (TextLoader, PyPDFLoader, CSVLoader, Docx2txtLoader)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

# Canonical project root and persistent Chroma directory
ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

PERSIST_DIRECTORY = str(ROOT / os.getenv("CHROMA_DIRECTORY", "db/chroma_local"))
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "rag_documents_v2")
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

logger = logging.getLogger("uvicorn.error")


def handle_upload(content: bytes, original_filename: str, session_id: str, document_id: str = None):
    """
    Saves uploaded file bytes, extracts text, splits into chunks,
    and indexes into ChromaDB with session_id and document_id metadata.
    """
    if not document_id:
        document_id = str(uuid4())

    ext = Path(original_filename).suffix.lower()

    # 1. Write uploaded bytes to a temporary file for loaders
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
        tmp_file.write(content)
        tmp_path = tmp_file.name

    try:
        # 2. Select loader based on file extension
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

        # 3. Split into overlapping chunks
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=700,
            chunk_overlap=120,
            separators=["\n\n", "\n", " ", ""]
        )
        chunks = text_splitter.split_documents(raw_docs)
        if not chunks:
            raise ValueError("Document yielded 0 chunks.")

        # 4. Attach session_id, document_id, filename and page metadata to every chunk
        for doc in chunks:
            doc.metadata["source"] = original_filename
            doc.metadata["filename"] = original_filename
            doc.metadata["session_id"] = str(session_id)
            doc.metadata["document_id"] = str(document_id)

        # 5. Create deterministic chunk IDs to prevent duplicate chunk indexing
        ids = [
            f"{session_id}:{document_id}:{i}"
            for i in range(len(chunks))
        ]

        # 6. Store in ChromaDB using canonical persistent directory
        embedding_model = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME)
        vectorstore = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=embedding_model,
            persist_directory=PERSIST_DIRECTORY,
            collection_metadata={"hnsw:space": "cosine"}
        )
        vectorstore.add_documents(documents=chunks, ids=ids)

        vectors_stored = len(ids)

        # 7. Diagnostic Logging
        logger.info(
            f"[UPLOAD] session_id={session_id} | document_id={document_id} | filename={original_filename} | "
            f"pages={num_pages} | chunks_created={len(chunks)} | vectors_stored={vectors_stored} | "
            f"collection={COLLECTION_NAME}"
        )

        return {
            "session_id": session_id,
            "document_id": document_id,
            "filename": original_filename,
            "pages": num_pages,
            "chunks": len(chunks),
            "vectors_stored": vectors_stored,
            "collection_name": COLLECTION_NAME
        }
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def list_all_documents():
    """Returns a list of all indexed documents with their chunk counts and page counts."""
    client = chromadb.PersistentClient(path=PERSIST_DIRECTORY)
    collection = client.get_or_create_collection(COLLECTION_NAME)
    all_data = collection.get(include=["metadatas"])

    summary = {}
    for m in all_data.get("metadatas", []):
        if not m:
            continue
        source = m.get("source") or m.get("filename") or "Unknown"
        filename = Path(source).name
        if filename not in summary:
            summary[filename] = {
                "filename": filename,
                "source": source,
                "chunks": 0,
                "pages": set(),
                "session_ids": set(),
                "document_ids": set()
            }
        summary[filename]["chunks"] += 1
        page = m.get("page")
        if page is not None:
            summary[filename]["pages"].add(page)
        sid = m.get("session_id")
        if sid:
            summary[filename]["session_ids"].add(sid)
        did = m.get("document_id")
        if did:
            summary[filename]["document_ids"].add(did)

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
            "document_ids": list(data["document_ids"])
        })

    return sorted(result, key=lambda x: x["filename"].lower())


def delete_document_by_name(filename: str):
    """Deletes all chunks associated with a source filename from ChromaDB."""
    client = chromadb.PersistentClient(path=PERSIST_DIRECTORY)
    collection = client.get_or_create_collection(COLLECTION_NAME)
    all_data = collection.get(include=["metadatas"])

    target_ids = []
    for cid, meta in zip(all_data.get("ids", []), all_data.get("metadatas", [])):
        if meta:
            src = meta.get("source", "")
            fname = meta.get("filename", "")
            if src == filename or fname == filename or Path(src).name == filename or Path(fname).name == filename:
                target_ids.append(cid)

    if not target_ids:
        raise ValueError(f"No indexed document found matching '{filename}'.")

    collection.delete(ids=target_ids)
    logger.info(f"[DELETE] Removed {len(target_ids)} chunks for file '{filename}' from collection '{COLLECTION_NAME}'")

    return {
        "success": True,
        "filename": filename,
        "deleted_chunks": len(target_ids),
        "remaining_chunks": collection.count()
    }