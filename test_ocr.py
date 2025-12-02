import io
import json
import re
import asyncio
import os
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from PIL import Image
import fitz  # PyMuPDF
import google.generativeai as genai

# ใช้ python-dotenv เพื่อโหลดค่าจากไฟล์ .env (ถ้ามี)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = FastAPI(title="OrgChart OCR API (Gemini 2.5 Flash)")

# --- CONFIGURATION ---
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

# เลือกโมเดล (แนะนำ Flash เพื่อความเร็วและประหยัด)
MODEL_NAME = 'gemini-2.5-flash-preview-09-2025'
model = genai.GenerativeModel(MODEL_NAME)

# ----------------------------
# PDF / Image → List of PIL Images
# ----------------------------
def pdf_or_image_to_images(file_bytes: bytes, filename):
    """แปลงไฟล์ PDF หรือรูปภาพให้เป็น list ของ PIL Image"""
    images = []
    filename_str = filename.decode() if isinstance(filename, bytes) else str(filename)

    # PDF Processing
    if filename_str.lower().endswith(".pdf"):
        try:
            doc = fitz.open("pdf", file_bytes)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid PDF file: {e}")

        for page in doc:
            # Render ที่ 300 DPI เพื่อความคมชัดสำหรับการทำ OCR
            pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            if img.mode != "RGB":
                img = img.convert("RGB")
            images.append(img)
        doc.close()
    
    # Image Processing
    elif filename_str.lower().endswith((".png", ".jpg", ".jpeg")):
        try:
            img = Image.open(io.BytesIO(file_bytes))
            if img.mode != "RGB":
                img = img.convert("RGB")
            images.append(img)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid image file: {e}")
    else:
        raise HTTPException(status_code=400, detail="File must be PDF, PNG, or JPG")
    return images

# ----------------------------
# Extract JSON from OCR Text
# ----------------------------
def extract_json(text: str):
    """พยายามแกะ JSON จากข้อความที่โมเดลตอบกลับมา"""
    try:
        # ค้นหาข้อความที่อยู่ในวงเล็บปีกกา {}
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            json_str = match.group(0)
            return json.loads(json_str)
        return {"natural_text": text}
    except Exception:
        return {"natural_text": text}

# ----------------------------
# Text processing helpers (Logic เดิมของคุณ)
# ----------------------------
def classify_text_block(text: str):
    """จำแนกประเภทข้อความว่าเป็น ชื่อ, ตำแหน่ง หรืออื่นๆ"""
    name_pattern = r"[A-Za-zก-๙]{2,50}\s+[A-Za-zก-๙]{2,50}"
    position_keywords = ["Manager", "Director", "หัวหน้า", "ผู้จัดการ", "CEO", "CTO", "COO", "Vice President", "Officer"]
    
    if any(k.lower() in text.lower() for k in position_keywords):
        return "position"
    elif re.match(name_pattern, text.strip()):
        return "name"
    else:
        return "other"

def extract_blocks_from_text(text: str):
    blocks = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            blocks.append({"text": line, "type": classify_text_block(line)})
    return blocks

def build_name_position_pairs(blocks):
    pairs = []
    last_position = None
    for b in blocks:
        if b["type"] == "position":
            last_position = b["text"]
        elif b["type"] == "name" and last_position:
            pairs.append({"position": last_position, "name": b["text"]})
            # last_position = None # Uncomment ถ้าต้องการ reset ตำแหน่งหลังจับคู่แล้ว
    return pairs

def build_hierarchy(blocks):
    hierarchy = {}
    stack = []
    for i, b in enumerate(blocks):
        if b["type"] != "position":
            continue
        level = i # ใช้ index เป็นตัวกำหนด level คร่าวๆ (อาจต้องปรับปรุง logic นี้ตาม layout จริง)
        while len(stack) > level:
            stack.pop()
        
        node = {b["text"]: {}}
        if not stack:
            hierarchy.update(node)
            stack.append(hierarchy[b["text"]])
        else:
            parent = stack[-1]
            # ตรวจสอบว่า parent เป็น dict หรือไม่ (ป้องกัน error)
            if isinstance(parent, dict):
                parent[b["text"]] = {}
                stack.append(parent[b["text"]])
    return hierarchy

# ----------------------------
# Gemini API Call Wrapper
# ----------------------------
async def call_gemini_ocr(img: Image.Image):
    """ส่งรูปภาพไปให้ Gemini ทำ OCR"""
    
    # ป้องกันการเรียก API ถ้าไม่มี Key
    if not GEMINI_API_KEY:
         raise HTTPException(status_code=500, detail="Gemini API Key missing on server.")

    # Prompt: สั่งให้ถอดข้อความและพยายามจัดรูปแบบ JSON ถ้าทำได้
    prompt = (
        "Transcribe the text from this organizational chart image exactly as it appears. "
        "Maintain the line structure. "
        "If possible, output the result as a JSON object with keys 'natural_text' containing the full text."
    )
    
    try:
        # ใช้ asyncio.to_thread เพื่อไม่ให้ block event loop ของ FastAPI ขณะรอ API
        response = await asyncio.to_thread(
            model.generate_content,
            [prompt, img]
        )
        return response.text
    except Exception as e:
        print(f"Gemini Error: {e}")
        # กรณี API Error ให้ raise กลับไปที่ endpoint เพื่อแจ้ง user
        raise HTTPException(status_code=500, detail=f"Gemini API Error: {str(e)}")

# ----------------------------
# Process one page (async)
# ----------------------------
async def process_page(img: Image.Image, page_number: int):
    # 1. เรียก OCR ผ่าน Gemini
    markdown = await call_gemini_ocr(img)

    # 2. แปลงผลลัพธ์
    parsed = extract_json(markdown)
    
    # ถ้า parse JSON ได้ ให้เอา field natural_text มาใช้ ถ้าไม่ได้ให้ใช้ text ทั้งหมด
    raw_text = parsed.get("natural_text", markdown)
    if isinstance(raw_text, list) or isinstance(raw_text, dict):
        raw_text = str(raw_text)

    # 3. ประมวลผลข้อความตาม Logic เดิม
    blocks = extract_blocks_from_text(raw_text)
    pairs = build_name_position_pairs(blocks)
    hierarchy = build_hierarchy(blocks)

    return {
        "page": page_number,
        "raw_text": raw_text,
        "blocks": blocks,
        "pairs": pairs,
        "hierarchy": hierarchy
    }

# ----------------------------
# Main async processing logic
# ----------------------------
async def process_file_async(file_bytes: bytes, filename):
    images = pdf_or_image_to_images(file_bytes, filename)

    # สร้าง Task เพื่อรัน OCR ทุกหน้าพร้อมกัน (Parallel Execution)
    tasks = [process_page(image, idx + 1) for idx, image in enumerate(images)]
    pages = await asyncio.gather(*tasks)

    # รวมผลลัพธ์
    all_pairs = []
    all_blocks = []
    all_hierarchy = {}
    for p in pages:
        all_pairs.extend(p["pairs"])
        all_blocks.extend(p["blocks"])
        all_hierarchy.update(p["hierarchy"])

    return {
        "total_pages": len(images),
        "combined_pairs": all_pairs,
        "combined_blocks": all_blocks,
        "combined_hierarchy": all_hierarchy,
        "pages": pages
    }

# ----------------------------
# API Endpoints
# ----------------------------
@app.post("/process-org-chart")
async def process_org_chart_endpoint(file: UploadFile = File(...)):
    """Endpoint สำหรับรับไฟล์ Org Chart (PDF/Image)"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded.")
    
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        result = await process_file_async(file_bytes, file.filename)
        return JSONResponse(content=result)
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {type(e).__name__}: {str(e)}")

@app.get("/health")
async def health():
    return {"status": "ok", "ocr_model": MODEL_NAME}