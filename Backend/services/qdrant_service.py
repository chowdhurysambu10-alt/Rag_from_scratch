import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from qdrant_client import QdrantClient, models
from langchain_qdrant import QdrantVectorStore

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

logger = logging.getLogger("uvicorn.error")

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "rag_documents_v2")
VECTOR_SIZE = 384  # sentence-transformers/all-MiniLM-L6-v2 dimension

_qdrant_client = None


def get_qdrant_client() -> QdrantClient:
    """Initialize and return a singleton QdrantClient instance.
    
    Validates environment variables and connects to Qdrant Cloud.
    Falls back gracefully to local memory mode only if explicitly configured for testing.
    """
    global _qdrant_client
    if _qdrant_client is not None:
        return _qdrant_client

    url = os.getenv("QDRANT_URL", "").strip()
    api_key = os.getenv("QDRANT_API_KEY", "").strip() or None

    if not url:
        raise ValueError(
            "QDRANT_URL is not configured. Please set QDRANT_URL and QDRANT_API_KEY "
            "in your .env file to connect to Qdrant Cloud."
        )

    try:
        if url == ":memory:":
            client = QdrantClient(":memory:")
        else:
            client = QdrantClient(
                url=url,
                api_key=api_key,
                timeout=30.0,
                prefer_grpc=False
            )
        _qdrant_client = client
        return _qdrant_client
    except Exception as e:
        logger.error(f"Failed to connect to Qdrant at {url}: {e}")
        raise RuntimeError(f"Could not connect to Qdrant: {e}")


def ensure_collection(client: QdrantClient = None, collection_name: str = None) -> bool:
    """Ensure the target collection exists in Qdrant with 384-dim Cosine configuration."""
    if client is None:
        client = get_qdrant_client()
    if collection_name is None:
        collection_name = os.getenv("QDRANT_COLLECTION", QDRANT_COLLECTION)

    try:
        if not client.collection_exists(collection_name):
            logger.info(f"Creating Qdrant collection '{collection_name}' (size={VECTOR_SIZE}, metric=Cosine)...")
            client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=VECTOR_SIZE,
                    distance=models.Distance.COSINE
                )
            )
            logger.info(f"Qdrant collection '{collection_name}' created successfully.")

        # Ensure keyword payload indexes exist for metadata filtering
        for field in ["metadata.session_id", "metadata.filename", "metadata.source", "metadata.document_id"]:
            try:
                client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field,
                    field_schema=models.PayloadSchemaType.KEYWORD
                )
            except Exception:
                pass  # Index already exists or not supported in mock
        return True
    except Exception as e:
        logger.error(f"Error checking/creating Qdrant collection '{collection_name}': {e}")
        raise


def get_qdrant_vector_store(embeddings, client: QdrantClient = None, collection_name: str = None) -> QdrantVectorStore:
    """Return a LangChain QdrantVectorStore instance configured with the active embedding model."""
    if client is None:
        client = get_qdrant_client()
    if collection_name is None:
        collection_name = os.getenv("QDRANT_COLLECTION", QDRANT_COLLECTION)

    ensure_collection(client, collection_name)

    return QdrantVectorStore(
        client=client,
        collection_name=collection_name,
        embedding=embeddings
    )
