import uvicorn
import os
from fastapi import FastAPI
from dotenv import load_dotenv

# โหลด .env
load_dotenv()

# สร้าง App หลักเพียงตัวเดียว
app = FastAPI(title="Unified Document Processing API")

# Import Router จากไฟล์ลูก
# (ข้อควรระวัง: ไฟล์ test_ocr.py และ test_pdf.py ต้องวางอยู่ข้างๆ ไฟล์ main.py)
from test_ocr import router as ocr_router
from test_pdf import router as pdf_router

# รวมร่าง Router เข้าสู่ App หลัก
app.include_router(ocr_router, tags=["Org Chart OCR"])
app.include_router(pdf_router, tags=["Smart Doc Processor"])

@app.get("/")
def home():
    return {
        "message": "API Running",
        "endpoints": [
            "/process-org-chart (from test_ocr.py)",
            "/process-document (from test_pdf.py)"
        ]
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)