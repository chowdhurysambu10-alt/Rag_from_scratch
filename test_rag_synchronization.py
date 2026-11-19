import os
import sys
import time
import requests
import pypdf
from pypdf.generic import DecodedStreamObject, NameObject, DictionaryObject
from pathlib import Path

API_BASE = "http://127.0.0.1:8000"

def create_pdf(filepath, lines):
    """Generate a clean PDF with the given lines of text using pypdf."""
    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    # Build PDF stream text
    stream_lines = ["BT", "/F1 12 Tf"]
    y = 720
    for line in lines:
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream_lines.append(f"50 {y} Td")
        stream_lines.append(f"({escaped}) Tj")
        y -= 25
        stream_lines.append(f"-50 {-25} Td") # reset delta
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

    with open(filepath, "wb") as f:
        writer.write(f)

def run_verification():
    print("=" * 70)
    print("STARTING RAG SYNCHRONIZATION VERIFICATION TEST")
    print("=" * 70)

    # 0. Health check
    res = requests.get(f"{API_BASE}/")
    assert res.status_code == 200, f"Health check failed: {res.text}"
    print("[PASS] Backend is alive and healthy.\n")

    # Prepare PDFs
    test_dir = Path("test_artifacts")
    test_dir.mkdir(exist_ok=True)
    tesla_pdf = test_dir / "Tesla.pdf"
    deloitte_pdf = test_dir / "Deloitte.pdf"
    google_pdf = test_dir / "Google.pdf"

    create_pdf(str(tesla_pdf), [
        "Tesla, Inc. Overview and Products",
        "Tesla, Inc. is an American electric vehicle and clean energy company headquartered in Austin, Texas.",
        "Tesla manufactures electric cars including the Model S, Model 3, Model X, Model Y, and Cybertruck.",
        "Tesla also manufactures Megapack and Powerwall battery energy storage systems.",
        "Elon Musk serves as the Chief Executive Officer of Tesla, Inc."
    ])

    create_pdf(str(deloitte_pdf), [
        "Deloitte Touche Tohmatsu Limited Overview",
        "Deloitte is a global professional services firm headquartered in London, England.",
        "Deloitte was founded in 1845 by William Welch Deloitte in London.",
        "It provides audit, consulting, financial advisory, risk management, and tax services.",
        "Deloitte is recognized as one of the Big Four accounting organizations."
    ])

    create_pdf(str(google_pdf), [
        "Google LLC and Alphabet Inc. Overview",
        "Google LLC is an American multinational technology company founded in 1998 by Larry Page and Sergey Brin.",
        "Google specializes in online advertising, search engine technology, cloud computing, and computer software.",
        "Its flagship products include Google Search, YouTube, Android, Google Cloud Platform, and Gmail.",
        "Sundar Pichai serves as the CEO of Alphabet Inc. and Google LLC."
    ])

    print(f"Created test PDF files in {test_dir}\n")

    # Step 1: Create a new chat session
    print("--- Step 1: Create a new chat (Session A) ---")
    session_res = requests.post(f"{API_BASE}/session")
    assert session_res.status_code == 200
    session_A = session_res.json()["session_id"]
    print(f"[PASS] Session A created with ID: {session_A}\n")

    # Step 2: Upload Tesla.pdf with session_A
    print("--- Step 2: Upload Tesla.pdf to Session A ---")
    with open(tesla_pdf, "rb") as f:
        res = requests.post(
            f"{API_BASE}/api/upload",
            files={"file": ("Tesla.pdf", f, "application/pdf")},
            data={"session_id": session_A}
        )
    assert res.status_code == 200, f"Upload Tesla failed: {res.text}"
    data = res.json()
    print(f"[PASS] Tesla.pdf uploaded: session_id={data['session_id']}, chunks={data['chunks']}, document_id={data['document_id']}\n")

    # Step 3: Upload Deloitte.pdf to session_A
    print("--- Step 3: Upload Deloitte.pdf to Session A ---")
    with open(deloitte_pdf, "rb") as f:
        res = requests.post(
            f"{API_BASE}/api/upload",
            files={"file": ("Deloitte.pdf", f, "application/pdf")},
            data={"session_id": session_A}
        )
    assert res.status_code == 200, f"Upload Deloitte failed: {res.text}"
    data = res.json()
    print(f"[PASS] Deloitte.pdf uploaded: session_id={data['session_id']}, chunks={data['chunks']}, document_id={data['document_id']}\n")

    # Step 4: Upload Google.pdf to session_A
    print("--- Step 4: Upload Google.pdf to Session A ---")
    with open(google_pdf, "rb") as f:
        res = requests.post(
            f"{API_BASE}/api/upload",
            files={"file": ("Google.pdf", f, "application/pdf")},
            data={"session_id": session_A}
        )
    assert res.status_code == 200, f"Upload Google failed: {res.text}"
    data = res.json()
    print(f"[PASS] Google.pdf uploaded: session_id={data['session_id']}, chunks={data['chunks']}, document_id={data['document_id']}\n")

    # Step 5: Ask a Tesla-related question in session_A
    print("--- Step 5: Ask a Tesla-related question in Session A ---")
    chat_res = requests.post(
        f"{API_BASE}/chat",
        json={"question": "What electric vehicles and products does Tesla manufacture?", "session_id": session_A}
    )
    assert chat_res.status_code == 200, f"Chat failed: {chat_res.text}"
    chat_data = chat_res.json()
    sources = [s["file"] for s in chat_data.get("sources", [])]
    print(f"Retrieved sources: {sources}")
    print(f"Answer snippet: {chat_data['answer'][:200]}...")
    assert any("Tesla" in s for s in sources), f"Tesla.pdf not found in retrieved sources: {sources}"
    print("[PASS] Tesla question successfully retrieved Tesla.pdf\n")

    # Step 6: Ask a Deloitte-related question in session_A
    print("--- Step 6: Ask a Deloitte-related question in Session A ---")
    chat_res = requests.post(
        f"{API_BASE}/chat",
        json={"question": "When was Deloitte founded and who was its founder?", "session_id": session_A}
    )
    assert chat_res.status_code == 200, f"Chat failed: {chat_res.text}"
    chat_data = chat_res.json()
    sources = [s["file"] for s in chat_data.get("sources", [])]
    print(f"Retrieved sources: {sources}")
    print(f"Answer snippet: {chat_data['answer'][:200]}...")
    assert any("Deloitte" in s for s in sources), f"Deloitte.pdf not found in retrieved sources: {sources}"
    print("[PASS] Deloitte question successfully retrieved Deloitte.pdf\n")

    # Step 7: Ask a Google-related question in session_A
    print("--- Step 7: Ask a Google-related question in Session A ---")
    chat_res = requests.post(
        f"{API_BASE}/chat",
        json={"question": "Who founded Google and what are its key products?", "session_id": session_A}
    )
    assert chat_res.status_code == 200, f"Chat failed: {chat_res.text}"
    chat_data = chat_res.json()
    sources = [s["file"] for s in chat_data.get("sources", [])]
    print(f"Retrieved sources: {sources}")
    print(f"Answer snippet: {chat_data['answer'][:200]}...")
    assert any("Google" in s for s in sources), f"Google.pdf not found in retrieved sources: {sources}"
    print("[PASS] Google question successfully retrieved Google.pdf\n")

    # Step 8: Verify that each answer retrieved the correct PDF
    print("--- Step 8: Cross-retrieval verification ---")
    print("[PASS] Verified: All 3 PDFs (Tesla, Deloitte, Google) are co-indexed under Session A and dynamically retrieved for their respective queries.\n")

    # Step 9: Start another new chat and verify session isolation
    print("--- Step 9: Start another new chat (Session B) and verify session isolation ---")
    session_res2 = requests.post(f"{API_BASE}/session")
    session_B = session_res2.json()["session_id"]
    print(f"Session B created with ID: {session_B}")

    # Query Tesla in Session B (should NOT return documents from Session A)
    chat_res_b = requests.post(
        f"{API_BASE}/chat",
        json={"question": "What products does Tesla manufacture?", "session_id": session_B}
    )
    assert chat_res_b.status_code == 200
    chat_data_b = chat_res_b.json()
    sources_b = chat_data_b.get("sources", [])
    print(f"Session B retrieved sources for Tesla query: {sources_b}")
    assert len(sources_b) == 0, f"Session isolation failed! Retrieved documents from session A in session B: {sources_b}"
    print("[PASS] Session isolation verified: 0 documents retrieved from Session A in Session B.\n")

    # Step 10: Test uploading another PDF into Session B without restarting FastAPI
    print("--- Step 10: Test uploading a PDF to Session B WITHOUT restarting FastAPI ---")
    amazon_pdf = test_dir / "Amazon.pdf"
    create_pdf(str(amazon_pdf), [
        "Amazon.com Inc. Overview",
        "Amazon is an American multinational technology company focusing on e-commerce, cloud computing, and digital streaming.",
        "It was founded by Jeff Bezos in 1994 in Bellevue, Washington.",
        "Amazon Web Services (AWS) provides on-demand cloud computing platforms and APIs."
    ])
    with open(amazon_pdf, "rb") as f:
        res = requests.post(
            f"{API_BASE}/api/upload",
            files={"file": ("Amazon.pdf", f, "application/pdf")},
            data={"session_id": session_B}
        )
    assert res.status_code == 200, f"Upload to session B failed: {res.text}"
    print(f"[PASS] Amazon.pdf uploaded to Session B.")

    # Immediately query in Session B
    chat_res_amazon = requests.post(
        f"{API_BASE}/chat",
        json={"question": "Who founded Amazon and what does AWS provide?", "session_id": session_B}
    )
    assert chat_res_amazon.status_code == 200
    amazon_data = chat_res_amazon.json()
    amazon_sources = [s["file"] for s in amazon_data.get("sources", [])]
    print(f"Retrieved sources for Amazon query in Session B: {amazon_sources}")
    print(f"Answer snippet: {amazon_data['answer'][:200]}...")
    assert any("Amazon" in s for s in amazon_sources), f"Amazon.pdf not retrieved in Session B: {amazon_sources}"
    print("[PASS] Immediate dynamic retrieval confirmed without restarting FastAPI!\n")

    print("=" * 70)
    print("ALL 10 VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    run_verification()
