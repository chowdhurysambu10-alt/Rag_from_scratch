#!/usr/bin/env python3
"""
Sync all documents from Qdrant Cloud into Supabase public.shared_documents table.
Ensures document metadata, chunks, and page counts are visible in Supabase Table Editor.
"""

import os
import sys
import uuid
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from Backend.services.qdrant_service import get_qdrant_client, QDRANT_COLLECTION
from Backend.services.ingestion_service import list_all_documents
from Backend.services.supabase_service import get_supabase_client


def sync_qdrant_to_supabase():
    print("=" * 70)
    print("SYNCING QDRANT CLOUD DOCUMENTS TO SUPABASE SHARED_DOCUMENTS")
    print("=" * 70)

    client = get_supabase_client()
    if not client:
        print("Error: Supabase client is not configured in .env")
        sys.exit(1)

    docs = list_all_documents()
    print(f"Found {len(docs)} unique documents in Qdrant Cloud collection '{QDRANT_COLLECTION}'")

    records = []
    for d in docs:
        filename = d.get("filename")
        records.append({
            "document_id": str(uuid.uuid4()),
            "filename": filename,
            "source": d.get("source") or filename,
            "chunks": d.get("chunks", 0),
            "pages": d.get("pages", 1),
            "uploaded_by": "Shared Knowledge Base",
            "status": "Indexed"
        })

    if not records:
        print("No documents found in Qdrant Cloud to sync.")
        return

    res = client.table("shared_documents").upsert(records, on_conflict="filename").execute()
    synced_count = len(res.data) if res.data else len(records)
    print(f"Successfully synced {synced_count} documents into Supabase 'shared_documents' table!")

    count_check = client.table("shared_documents").select("count", count="exact").execute()
    print(f"Total rows in Supabase shared_documents now: {count_check.count}")
    print("=" * 70)


if __name__ == "__main__":
    sync_qdrant_to_supabase()
