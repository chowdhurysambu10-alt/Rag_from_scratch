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

def load_documents(folder="docs"):
    documents = []

    for file in Path(folder).rglob("*"):
        if not file.is_file():
            continue

        ext = file.suffix.lower()

        if ext in [".txt", ".py", ".cpp", ".h"]:
            loader = TextLoader(
                str(file),
                encoding="utf-8",
                autodetect_encoding=True
            )

        elif ext == ".pdf":
            loader = PyPDFLoader(str(file))

        elif ext == ".csv":
            loader = CSVLoader(
                file_path=str(file),
                autodetect_encoding=True
            )

        elif ext == ".docx":
            loader = Docx2txtLoader(str(file))

        else:
            continue

        documents.extend(loader.load())

    return documents



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
    documents = load_documents("docs")  
    
  # Step 2: Split into chunks   
    chunks = split_documents(documents)

    # # Step 3: Create vector store
    vectorstore = create_vector_store(chunks)

if __name__ == "__main__":
    main()