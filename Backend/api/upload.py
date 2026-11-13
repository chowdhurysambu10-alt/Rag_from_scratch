
from fastapi import APIRouter, UploadFile, File, HTTPException
from Backend.services.ingestion_service import handle_upload
router = APIRouter()

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


@router.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):

    # 1. Validate filename
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported."
        )

    # 2. Read uploaded file
    content = await file.read()

    # 3. Validate size
    if not content:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is empty."
        )

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="Maximum file size is 20 MB."
        )

    # 4. Validate PDF signature
    if not content.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=400,
            detail="Invalid PDF file."
        )

    try:
        # 5. Call ingestion service
        result = handle_upload(
            content=content,
            original_filename=file.filename
        )

        return {
            "success": True,
            "message": "Document uploaded and indexed successfully.",
            **result
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Document processing failed: {str(e)}"
        )

    finally:
        await file.close()
