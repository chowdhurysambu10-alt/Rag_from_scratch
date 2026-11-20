"""
Migration Script: Local ChromaDB -> Qdrant Cloud
Safely transfers vectors, documents, and metadata from local ChromaDB to Qdrant Cloud.
Keeps the existing ChromaDB files completely intact as a backup.
"""

import os
import sys
import uuid
import logging
from pathlib import Path
from dotenv import load_dotenv

import chromadb
from qdrant_client import models
from Backend.services.qdrant_service import (
    get_qdrant_client,
    ensure_collection,
    QDRANT_COLLECTION,
    VECTOR_SIZE
)

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migration")

CHROMA_DIR = ROOT / os.getenv("CHROMA_DIRECTORY", "db/chroma_local")
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "rag_documents_v2")
TARGET_QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", QDRANT_COLLECTION)
BATCH_SIZE = 150


def run_migration(dry_run: bool = False):
    print("=" * 70)
    print("CHROMA TO QDRANT CLOUD MIGRATION TOOL")
    print("=" * 70)

    # 1. Inspect ChromaDB
    if not CHROMA_DIR.exists():
        logger.error(f"Local ChromaDB directory not found at: {CHROMA_DIR}")
        sys.exit(1)

    logger.info(f"Opening local ChromaDB at: {CHROMA_DIR}")
    chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    try:
        chroma_col = chroma_client.get_collection(CHROMA_COLLECTION)
    except Exception as e:
        logger.error(f"Collection '{CHROMA_COLLECTION}' not found in ChromaDB: {e}")
        sys.exit(1)

    total_chroma_points = chroma_col.count()
    logger.info(f"Found collection '{CHROMA_COLLECTION}' with {total_chroma_points} total vectors in ChromaDB.")

    if total_chroma_points == 0:
        logger.warning("ChromaDB collection is empty. Nothing to migrate.")
        return

    # 2. Inspect Qdrant Cloud
    logger.info("Connecting to Qdrant Cloud...")
    try:
        qdrant_client = get_qdrant_client()
    except Exception as e:
        logger.error(f"Failed to connect to Qdrant: {e}")
        logger.error("Please verify that QDRANT_URL and QDRANT_API_KEY are properly set in your .env file.")
        sys.exit(1)

    if not dry_run:
        ensure_collection(qdrant_client, TARGET_QDRANT_COLLECTION)
        initial_qdrant_count = qdrant_client.count(TARGET_QDRANT_COLLECTION).count
        logger.info(f"Target Qdrant collection '{TARGET_QDRANT_COLLECTION}' currently has {initial_qdrant_count} vectors.")
    else:
        logger.info("[DRY RUN] Will not write any vectors to Qdrant Cloud.")

    # 3. Read ChromaDB in batches and prepare Qdrant points
    logger.info(f"Beginning batch migration (batch size = {BATCH_SIZE})...")

    # Fetch all IDs first to paginate safely
    all_chroma_data = chroma_col.get(include=["metadatas"])
    all_ids = all_chroma_data.get("ids", [])
    total_ids = len(all_ids)

    migrated_count = 0

    for i in range(0, total_ids, BATCH_SIZE):
        batch_ids = all_ids[i : i + BATCH_SIZE]
        batch_data = chroma_col.get(
            ids=batch_ids,
            include=["embeddings", "documents", "metadatas"]
        )

        batch_points = []
        for cid, emb, doc, meta in zip(
            batch_data["ids"],
            batch_data["embeddings"],
            batch_data["documents"],
            batch_data["metadatas"]
        ):
            # Deterministic UUID for Qdrant based on Chroma ID
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, cid))

            # LangChain QdrantVectorStore expects payload schema:
            # {"page_content": text, "metadata": dict}
            payload = {
                "page_content": doc or "",
                "metadata": meta or {}
            }

            batch_points.append(
                models.PointStruct(
                    id=point_id,
                    vector=emb,
                    payload=payload
                )
            )

        if not dry_run:
            qdrant_client.upsert(
                collection_name=TARGET_QDRANT_COLLECTION,
                points=batch_points,
                wait=True
            )

        migrated_count += len(batch_points)
        progress = (migrated_count / total_ids) * 100
        logger.info(f"Migrated {migrated_count}/{total_ids} points ({progress:.1f}%)...")

    # 4. Final verification
    print("-" * 70)
    if not dry_run:
        final_qdrant_count = qdrant_client.count(TARGET_QDRANT_COLLECTION).count
        logger.info(f"MIGRATION COMPLETE!")
        logger.info(f"ChromaDB Source Vectors: {total_chroma_points}")
        logger.info(f"Qdrant Cloud Final Vectors: {final_qdrant_count}")
        logger.info(f"Local ChromaDB backup preserved untouched at: {CHROMA_DIR}")
    else:
        logger.info(f"[DRY RUN COMPLETE] {migrated_count} points validated for migration.")
    print("=" * 70)


if __name__ == "__main__":
    is_dry = "--dry-run" in sys.argv
    run_migration(dry_run=is_dry)
