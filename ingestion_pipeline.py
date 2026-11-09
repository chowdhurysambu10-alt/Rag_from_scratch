import os
from typing import List, Union
from langchain_community.document_loaders import TextLoader, DirectoryLoader, PyPDFLoader, CSVLoader
from langchain_text_splitters import CharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from dotenv import load_dotenv

load_dotenv()


# Document loading part ->

def load_documents(docs_sources: Union[str, List[str]] = "docs", docs_path: Union[str, List[str], None] = None):
    """
    Load documents from multiple inputs (directories or files)
    and supports multiple formats (.txt, .pdf, .csv, .md).
    
    Args:
        docs_sources: A single path string or a list of path strings (folders or files).
        docs_path: Alias for docs_sources for backward compatibility.
    """
    if docs_path is not None:
        docs_sources = docs_path
    print(f"Loading documents from sources: {docs_sources}...")

    # Normalize to list if a single path is provided
    if isinstance(docs_sources, str):
        docs_sources = [docs_sources]

    loader_mapping = {
        ".txt": (TextLoader, {"encoding": "utf-8"}),
        ".md": (TextLoader, {"encoding": "utf-8"}),
        ".csv": (CSVLoader, {"encoding": "utf-8"}),
        ".pdf": (PyPDFLoader, {}),
    }

    documents = []

    def _load_file(file_path: str):
        ext = os.path.splitext(file_path)[1].lower()
        if ext in loader_mapping:
            loader_cls, kwargs = loader_mapping[ext]
            try:
                loader = loader_cls(file_path, **kwargs)
                loaded = loader.load()
                print(f"  Loaded {len(loaded)} doc(s) from: {file_path}")
                return loaded
            except Exception as e:
                print(f"  Error loading {file_path}: {e}")
                return []
        return []

    for src in docs_sources:
        if not os.path.exists(src):
            print(f"Warning: Path '{src}' does not exist. Skipping.")
            continue

        if os.path.isfile(src):
            documents.extend(_load_file(src))
        elif os.path.isdir(src):
            print(f"Scanning directory: {src}...")
            found_any = False
            for root, _, files in os.walk(src):
                for file in sorted(files):
                    ext = os.path.splitext(file)[1].lower()
                    if ext in loader_mapping:
                        full_path = os.path.join(root, file)
                        documents.extend(_load_file(full_path))
                        found_any = True
            if not found_any:
                print(f"No supported files ({', '.join(loader_mapping.keys())}) found in {src}.")

    if len(documents) == 0:
        raise FileNotFoundError(f"No documents could be loaded from: {docs_sources}")

    print(f"\nTotal documents loaded: {len(documents)}")
    for i, doc in enumerate(documents[:2]):  # Show first 2 documents
        print(f"\nDocument {i+1}:")
        print(f"  Source: {doc.metadata.get('source', 'Unknown')}")
        print(f"  Content length: {len(doc.page_content)} characters")
        print(f"  Content preview: {doc.page_content[:100]}...")
        print(f"  metadata: {doc.metadata}")

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

    print(f"\nCreating embeddings for {len(chunks)} chunks and storing in ChromaDB...")
    print("Please wait, generating embeddings on CPU may take 20-40 seconds...")

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


# main function

def main():
    print("Main Function")
    
    # Step 1: Load documents
    # You can pass a single directory, a single file, or a list of multiple files/folders:
    # Example 1 (Directory): load_documents("docs")
    # Example 2 (Multiple inputs): load_documents(["docs", "extra_files/report.pdf", "data/info.csv"])
    documents = load_documents(docs_sources="docs")  
    
    # Step 2: Split into chunks   
    chunks = split_documents(documents)

    # Step 3: Create vector store
    vectorstore = create_vector_store(chunks)
    
    
if __name__ == "__main__":
    main()