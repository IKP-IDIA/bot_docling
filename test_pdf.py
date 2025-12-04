import os
import re
import uuid
import json
import asyncio
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import fitz  # PyMuPDF (ใช้สำหรับ Fallback กรณี Docling พลาด - เฉพาะ PDF)
from PIL import Image
import io
import google.generativeai as genai
from docling.document_converter import DocumentConverter # นำ Docling กลับมา

# ใช้ python-dotenv เพื่อโหลดค่าจากไฟล์ .env (ถ้ามี)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

router = APIRouter()

# -------------------------------
# Config
# -------------------------------
# ⚠️⚠️⚠️ SECURE VERSION: ดึง Key จาก Environment Variable ⚠️⚠️⚠️
# ห้ามใส่ Key จริงลงในไฟล์นี้ถ้าจะเอาขึ้น Git
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ตรวจสอบว่าใส่ Key หรือยัง
if not GEMINI_API_KEY:
    print("\n" + "="*60)
    print("❌ CRITICAL ERROR: ไม่พบ GEMINI_API_KEY ใน Environment Variable")
    print("   วิธีแก้ไข: สร้างไฟล์ .env และใส่ GEMINI_API_KEY=your_key_here")
    print("="*60 + "\n")
else:
    # ตั้งค่า API เฉพาะเมื่อมี Key แล้ว
    try:
        genai.configure(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"Error configuring Gemini: {e}")

MODEL_NAME = 'gemini-2.5-flash-preview-09-2025'
model = genai.GenerativeModel(MODEL_NAME)

MEILI_URL = "http://10.1.0.150:7700/indexes/documents/documents"

# --------------------------------------------------
# Utilities
# --------------------------------------------------
def generate_keywords_from_filename(filename):
    base = os.path.basename(filename)
    name, _ = os.path.splitext(base)
    words = re.split(r"[\s._-]+", name)
    return [w for w in words if not w.isdigit() and len(w) > 1]

def check_filename_keywords(text, filename):
    keywords = generate_keywords_from_filename(filename)
    text_lower = text.lower()
    for kw in keywords:
        if kw.lower() in text_lower:
            return "เนื้อหาสอดคล้อง"
    return "เนื้อหาไม่สอดคล้อง"

def pdf_to_images(file_path):
    """Fallback: แปลง PDF เป็นรูปภาพกรณี Docling อ่านไม่ออก"""
    try:
        doc = fitz.open(file_path)
        images = []
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            if img.mode != "RGB":
                img = img.convert("RGB")
            images.append(img)
        doc.close()
        return images
    except Exception as e:
        print(f"Error converting PDF: {e}")
        return []

# --------------------------------------------------
# Gemini Logic
# --------------------------------------------------
async def analyze_with_gemini(content, is_image=False):
    """
    ฟังก์ชันเดียวรองรับทั้ง Text (จาก Docling) และ Image (Fallback)
    """
    
    # ป้องกันการเรียก API ถ้าไม่มี Key
    if not GEMINI_API_KEY:
        return {
            "doc_type": "Config Error",
            "extracted_info": "❌ Error: Server Environment Variable 'GEMINI_API_KEY' not set."
        }

    base_prompt = """
    You are an intelligent document processing AI. Analyze the provided document content.
    
    Task 1: Classify the document into ONE of these categories:
       1. ข้อมูลที่เกี่ยวข้องกับการประกอบธุรกิจ บัตรเครดิต
       2. ทะเบียนผู้ถือหุ้นของบริษัทฉบับล่าสุด
       3. เอกสารแสดงฐานะทางการเงิน
       4. มติคณะกรรมการบริษัท / เอกสารอนุมัติ
       5. โครงสร้างองค์กร
       6. โครงสร้างกลุ่มธุรกิจ
       7. นโยบายและคู่มือปฏิบัติงาน
       (If unsure, use "Unknown")

    Task 2: Extract specific information based on the identified category:
       - If Type 1: Extract "Time period for customer contact" (e.g., 09:00-17:00).
       - If Type 2 or 6: Extract "Shareholder ratio" (e.g., 99.99%).
       - If Type 3: Return "Financial Status Checked".
       - If Type 4: Extract "License Number".
       - Else: Return "No specific info".

    Output Requirements:
    Return ONLY a valid JSON object with this structure:
    {
        "doc_type": "Number + Category Name",
        "extracted_info": "..."
    }
    """
    
    try:
        inputs = [base_prompt]
        if is_image:
            # content คือ list ของรูปภาพ
            inputs.extend(content)
        else:
            # content คือ text markdown
            inputs.append(f"\n\nDocument Content (Markdown):\n{content[:30000]}") # Limit text length if needed

        response = await asyncio.to_thread(
            model.generate_content,
            inputs
        )
        
        text_resp = response.text
        # Clean JSON
        if "```json" in text_resp:
            text_resp = text_resp.split("```json")[1].split("```")[0].strip()
        elif "```" in text_resp:
            text_resp = text_resp.split("```")[1].split("```")[0].strip()
            
        return json.loads(text_resp)
        
    except Exception as e:
        print(f"Gemini Processing Error: {e}")
        return {
            "doc_type": "Error",
            "extracted_info": f"Error: {str(e)}"
        }

# --------------------------------------------------
# MAIN PROCESS FUNCTION
# --------------------------------------------------
async def process_document_logic(file_path: str, filename: str):
    
    # 0. Check Key First
    if not GEMINI_API_KEY:
         return {
            "id": "ERROR",
            "filename_only": filename,
            "filename_check": "API Key Missing",
            "doc_type": "Config Error",
            "extracted_info": "❌ กรุณาตั้งค่า GEMINI_API_KEY ใน Environment Variable หรือไฟล์ .env",
            "extraction_method": "-"
        }

    full_text = ""
    ai_result = {}
    extraction_method = "Unknown"
    
    # ตรวจสอบนามสกุลไฟล์
    file_ext = os.path.splitext(filename)[1].lower()

    # 1. พยายามใช้ Docling ก่อน (Docling รองรับ PDF, DOCX, XLSX, HTML, ฯลฯ)
    try:
        print(f"Processing with Docling: {filename}")
        converter = DocumentConverter()
        # Docling convert เป็น blocking operation อาจจะช้าถ้าไฟล์ใหญ่
        # รันใน thread เพื่อไม่ให้ block FastAPI
        result = await asyncio.to_thread(converter.convert, file_path)
        full_text = result.document.export_to_markdown()
        
        if not full_text.strip():
            raise Exception("Docling returned empty text")
            
        # ถ้า Docling สำเร็จ -> ส่ง Text ให้ Gemini วิเคราะห์
        ai_result = await analyze_with_gemini(full_text, is_image=False)
        extraction_method = "Docling"
        
    except Exception as e:
        print(f"Docling failed ({e})")
        
        # 2. Fallback Logic
        # ถ้าเป็น PDF: ลองใช้ Gemini Vision (แปลงเป็นรูปภาพ)
        if file_ext == '.pdf':
            print("Switching to Gemini Vision Fallback (PDF only)...")
            images = pdf_to_images(file_path)
            if images:
                ai_result = await analyze_with_gemini(images, is_image=True)
                full_text = "(Transcribed by Gemini Vision)"
                extraction_method = "Gemini Vision"
            else:
                ai_result = {"doc_type": "Error", "extracted_info": "Failed both Docling and Vision"}
                extraction_method = "Failed"
        else:
            # ถ้าเป็น DOCX/XLSX: ไม่มี Fallback Vision ง่ายๆ (ต้องใช้ LibreOffice ซึ่งยุ่งยาก)
            ai_result = {
                "doc_type": "Error", 
                "extracted_info": f"Docling failed for {file_ext} file and no image fallback available."
            }
            extraction_method = "Failed"

    # 3. รับผลลัพธ์
    doc_type = ai_result.get("doc_type", "Unknown")
    extracted_info = ai_result.get("extracted_info", "-")

    # 4. เช็คชื่อไฟล์
    filename_check = check_filename_keywords(full_text, filename)

    # 5. เตรียม JSON Output
    doc_id = "DL" + str(uuid.uuid4())
    now_str = datetime.now().isoformat()

    data = {
        "id": doc_id,
        "filename_only": filename,
        "file_path": file_path,
        "folder_path": os.path.dirname(file_path),
        "date": now_str,
        "filename_check": filename_check,
        "doc_type": doc_type,
        "extracted_info": extracted_info,
        "extraction_method": extraction_method
    }
    return data

# --------------------------------------------------
# FastAPI Endpoints
# --------------------------------------------------

# Endpoint ใหม่ รองรับทุกไฟล์
@router.post("/process-document")
async def process_document(file: UploadFile = File(...)):
    
    # ตรวจสอบนามสกุลไฟล์เบื้องต้น
    allowed_extensions = ['.pdf', '.docx', '.xlsx']
    file_ext = os.path.splitext(file.filename)[1].lower()
    
    if file_ext not in allowed_extensions:
         raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {allowed_extensions}")

    safe_filename = f"temp_{uuid.uuid4()}{file_ext}"
    with open(safe_filename, "wb") as f:
        f.write(await file.read())

    try:
        result = await process_document_logic(safe_filename, file.filename)
    finally:
        if os.path.exists(safe_filename):
            os.remove(safe_filename)

    return result

# Endpoint เก่า (เก็บไว้เพื่อ Backward Compatibility)
@router.post("/process-pdf")
async def process_pdf(file: UploadFile = File(...)):
    return await process_document(file)


@router.get("/")
def home():
    return {
        "message": "FastAPI Smart Doc Processor (PDF, DOCX, XLSX) is running",
        "usage": "POST /process-document (upload file)"
    }