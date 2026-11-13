import os
from langchain_community.document_loaders import TextLoader, DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from pathlib import Path
import hashlib
from langchain_community.document_loaders import (
    TextLoader,
    PyPDFLoader,
    CSVLoader,
    Docx2txtLoader
)
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

# Document loding part ->

import tempfile

def handle_upload(content: bytes, original_filename: str, session_id: str):
    """
    Saves uploaded file bytes, extracts text by file type,
    splits into chunks, and indexes into an isolated ChromaDB collection.
    """
    ext = Path(original_filename).suffix.lower()
    collection_name = f"session_{session_id}"
    persist_dir = os.getenv("CHROMA_DIRECTORY", "db/chroma_local")
    embedding_model_name = os.getenv(
        "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
    )
    # 1. Write uploaded bytes to a temporary file so loaders can read it
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
        tmp_file.write(content)
        tmp_path = tmp_file.name
    try:
        # 2. Select the right loader based on file extension
        if ext == ".pdf":
            loader = PyPDFLoader(tmp_path)
        elif ext in [".txt", ".py", ".cpp", ".h"]:
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
        # Attach original filename and session metadata to every page/chunk
        for doc in raw_docs:
            doc.metadata["source"] = original_filename
            doc.metadata["session_id"] = session_id
        # 3. Split into overlapping chunks
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=700,
            chunk_overlap=120,
            separators=["\n\n", "\n", " ", ""]
        )
        chunks = text_splitter.split_documents(raw_docs)
        # 4. Create deterministic chunk IDs (prevents duplicate indexing)
        ids = [
            hashlib.sha256(
                f"{session_id}:{original_filename}:{chunk.page_content}".encode("utf-8")
            ).hexdigest()
            for chunk in chunks
        ]
        # 5. Store in ChromaDB collection isolated by session_id
        embedding_model = HuggingFaceEmbeddings(model_name=embedding_model_name)
        vectorstore = Chroma(
            collection_name=collection_name,
            embedding_function=embedding_model,
            persist_directory=persist_dir,
            collection_metadata={"hnsw:space": "cosine"}
        )
        vectorstore.add_documents(documents=chunks, ids=ids)
        return {
            "session_id": session_id,
            "document_id": session_id,
            "filename": original_filename,
            "chunks": len(chunks),
            "collection_name": collection_name
        }
    finally:
        # Clean up temporary disk file
        if os.path.exists(tmp_path):
            os.remove(tmp_path)



# Document spliting part ->

model = SentenceTransformer(
    "sentence-transformers/all-MiniLM-L6-v2"
)

# Document splitting part
def split_documents(documents):
    """Split documents into overlapping chunks."""

    print("Splitting documents into chunks...")

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=700,
        chunk_overlap=120,
        length_function=len,
        separators=["\n\n", "\n", " ", ""]
    )

    chunks = text_splitter.split_documents(documents)

    print(f"Total chunks created: {len(chunks)}")
    print(f"Model token limit: {model.max_seq_length}")

    # Print first 2 chunks
    for i, chunk in enumerate(chunks[:2]):
        print(f"\nChunk {i+1}:")
        print(f"Source: {chunk.metadata.get('source')}")
        print(f"Length: {len(chunk.page_content)}")
        print(f"Preview: {chunk.page_content[:100]}...")

    # Validate token count
    for i, chunk in enumerate(chunks):
        token_count = len(
            model.tokenizer.encode(
                chunk.page_content,
                add_special_tokens=True,
                truncation=False
            )
        )

        if token_count > model.max_seq_length:
            print(
                f"Warning: Chunk {i+1} has "
                f"{token_count} tokens!"
            )

    return chunks


# creat vector storage ->


def create_vector_store(
    chunks,
    persist_directory="db/chroma_local"
):
    """Create or update ChromaDB without duplicate chunk IDs."""

    print("Initializing ChromaDB...")

    embedding_model = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )

    vectorstore = Chroma(
        collection_name="rag_documents_v2",
        embedding_function=embedding_model,
        persist_directory=persist_directory,
        collection_metadata={"hnsw:space": "cosine"}
    )

    if not chunks:
        print("No chunks to ingest.")
        return vectorstore

    ids = []

    for chunk in chunks:
        source = chunk.metadata.get("source", "unknown")
        content = chunk.page_content

        # Stable ID based on source and chunk content
        raw_id = f"{source}:{content}"

        chunk_id = hashlib.sha256(
            raw_id.encode("utf-8")
        ).hexdigest()

        ids.append(chunk_id)

    # Remove identical source/content records in one batch
    unique_chunks = {}
    for chunk_id, chunk in zip(ids, chunks):
        unique_chunks[chunk_id] = chunk

    # Existing IDs will be updated, not appended
    vectorstore.add_documents(
        documents=list(unique_chunks.values()),
        ids=list(unique_chunks.keys())
    )

    print(f"Ingested {len(unique_chunks)} unique chunks.")
    print(f"Total stored chunks: {vectorstore._collection.count()}")

    return vectorstore


# main functiin and 

def main():
    print("Main Function")
    
 # Step 1: Load documents
    documents = handle_upload("docs")
    
  # Step 2: Split into chunks   
    chunks = split_documents(documents)

    # # Step 3: Create vector store
    vectorstore = create_vector_store(chunks)

if __name__ == "__main__":
    main()