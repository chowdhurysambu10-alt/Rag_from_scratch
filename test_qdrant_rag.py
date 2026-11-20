"""
Verification Test Suite: Qdrant Cloud RAG Pipeline
Tests connection, collection setup, ingestion, retrieval, session filtering, deletion, and cross-session isolation.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

import pypdf
from pypdf.generic import DecodedStreamObject, NameObject, DictionaryObject
from langchain_core.documents import Document

from Backend.services.qdrant_service import (
    get_qdrant_client,
    ensure_collection,
    get_qdrant_vector_store,
    QDRANT_COLLECTION,
    VECTOR_SIZE
)
from Backend.services.ingestion_service import (
    handle_upload,
    list_all_documents,
    delete_document_by_name
)
from history_aware_generation import get_retriever, get_embeddings, ask_question, get_model


def create_pdf_bytes(title: str, lines: list) -> bytes:
    """Create a minimal valid PDF in memory."""
    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    stream_lines = ["BT", "/F1 12 Tf", f"50 720 Td", f"({title}) Tj"]
    y = 690
    for line in lines:
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream_lines.append(f"50 {y} Td")
        stream_lines.append(f"({escaped}) Tj")
        y -= 25
        stream_lines.append(f"-50 {-25} Td")
    stream_lines.append("ET\n")

    stream_content = "\n".join(stream_lines).encode("latin1")
    stream_obj = DecodedStreamObject()
    stream_obj.set_data(stream_content)
    stream_ref = writer._add_object(stream_obj)
    page[NameObject("/Contents")] = stream_ref

    font_dict = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica")
    })
    font_ref = writer._add_object(font_dict)
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({
            NameObject("/F1"): font_ref
        })
    })

    import io
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def run_qdrant_tests():
    print("=" * 70)
    print("STARTING QDRANT RAG INTEGRATION VERIFICATION")
    print("=" * 70)

    # 1. Connection check
    print("\n[Test 1] Testing Qdrant Client connection...")
    client = get_qdrant_client()
    print(f"Successfully connected to Qdrant!")

    # 2. Collection initialization
    print("\n[Test 2] Ensuring Qdrant collection exists...")
    ensure_collection(client, QDRANT_COLLECTION)
    col_info = client.get_collection(QDRANT_COLLECTION)
    print(f"Collection '{QDRANT_COLLECTION}' verified. Vector dimension: {col_info.config.params.vectors.size}, Metric: {col_info.config.params.vectors.distance}")
    assert col_info.config.params.vectors.size == VECTOR_SIZE, f"Dimension mismatch: expected {VECTOR_SIZE}, got {col_info.config.params.vectors.size}"

    # 3. Dynamic Upload & Ingestion
    print("\n[Test 3] Testing dynamic document upload...")
    session_1 = "test_session_alpha"
    tesla_bytes = create_pdf_bytes("Tesla Inc Overview", [
        "Tesla, Inc. designs, develops, and manufactures electric vehicles including Model S, Model 3, Model X, Model Y, and Cybertruck.",
        "Tesla also builds Megapack and Powerwall battery storage systems.",
        "Elon Musk serves as Chief Executive Officer of Tesla."
    ])

    upload_res = handle_upload(
        content=tesla_bytes,
        original_filename="Tesla_Test.pdf",
        session_id=session_1
    )
    print(f"Upload success: filename={upload_res['filename']}, chunks={upload_res['chunks']}, session_id={upload_res['session_id']}")
    assert upload_res["chunks"] > 0

    # 4. Immediate retrieval without restart
    print("\n[Test 4] Testing immediate retrieval from Qdrant...")
    embeddings = get_embeddings()
    retriever = get_retriever(embeddings, session_id=None)
    docs = retriever.invoke("What electric vehicle models does Tesla make?")
    print(f"Retrieved {len(docs)} documents.")
    for d in docs:
        print(f" - Doc source: {d.metadata.get('source')} | preview: {d.page_content[:60]}...")
    assert any("Tesla" in d.metadata.get("source", "") for d in docs), "Tesla_Test.pdf was not retrieved!"
    print("Retrieval verified successfully!")

    # 5. Session isolation filtering
    print("\n[Test 5] Testing session-based metadata filtering...")
    session_retriever = get_retriever(embeddings, session_id="non_existent_session_xyz")
    isolated_docs = session_retriever.invoke("What does Tesla make?")
    print(f"Isolated search in empty session returned: {len(isolated_docs)} documents.")
    assert len(isolated_docs) == 0, "Session isolation failed! Retrieved documents from another session."
    print("Session isolation verified: 0 documents retrieved from different session!")

    # 6. List all documents (Dashboard integration)
    print("\n[Test 6] Testing list_all_documents (My Documents)...")
    docs_list = list_all_documents()
    print(f"Total documents found in Qdrant: {len(docs_list)}")
    for d in docs_list:
        if d["filename"] == "Tesla_Test.pdf":
            print(f" - Found indexed file: {d['filename']} with {d['chunks']} chunks and pages={d['pages']}")
    assert any(d["filename"] == "Tesla_Test.pdf" for d in docs_list), "Tesla_Test.pdf not found in document list!"

    # 7. Document Deletion
    print("\n[Test 7] Testing document deletion by filename...")
    del_res = delete_document_by_name("Tesla_Test.pdf")
    print(f"Deleted {del_res['deleted_chunks']} chunks for Tesla_Test.pdf. Remaining: {del_res['remaining_chunks']}")
    assert del_res["deleted_chunks"] > 0

    # Verify document is gone from retrieval
    retriever_after_del = get_retriever(embeddings, session_id=None)
    docs_after = retriever_after_del.invoke("Tesla Model S and Cybertruck")
    sources_after = [d.metadata.get("source", "") for d in docs_after]
    assert "Tesla_Test.pdf" not in sources_after, "Deleted document was still retrieved!"
    print("Deletion verified: document no longer appears in search results!")

    print("\n" + "=" * 70)
    print("ALL QDRANT INTEGRATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    run_qdrant_tests()
