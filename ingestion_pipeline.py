import os
from langchain_community.document_loaders import TextLoader, DirectoryLoader
from langchain_text_splitters import CharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from pathlib import Path
from langchain_community.document_loaders import (
    TextLoader,
    PyPDFLoader,
    CSVLoader,
    Docx2txtLoader
)
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

def split_documents(documents, chunk_size=1000, chunk_overlap=0):
    """Split documents into smaller chunks with overlap"""
    print("Splitting documents into chunks...")
    
    text_splitter = CharacterTextSplitter(
        chunk_size=chunk_size, 
        chunk_overlap=chunk_overlap
    )
    
    chunks = text_splitter.split_documents(documents)
    
    if chunks:
    
        for i, chunk in enumerate(chunks[:3]):
            print(f"\n--- Chunk {i+1} ---")
            print(f"Source: {chunk.metadata['source']}")
            print(f"Length: {len(chunk.page_content)} characters")
            print(f"Content:")
            print(chunk.page_content)
            print("-" * 50)
        
        if len(chunks) > 5:
            print(f"\n... and {len(chunks) - 5} more chunks")
    
    return chunks

# creat vector storage ->


def create_vector_store(chunks, persist_directory="db/chroma_local"):
    """Create and persist ChromaDB vector store"""

    print("Creating embeddings and storing in ChromaDB...")

    embedding_model = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )

    # Create ChromaDB vector store
    print("--- Creating vector store ---")

    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embedding_model,
        persist_directory=persist_directory,
        collection_metadata={"hnsw:space": "cosine"}
    )

    print("--- Finished creating vector store ---")
    print(f"Vector store created and saved to {persist_directory}")

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