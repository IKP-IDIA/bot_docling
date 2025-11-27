import os
import re
import pypdfium2 as pdfium
import pytesseract
from PIL import Image

# ------------------------------
# CONFIG
# ------------------------------
pdf_path = r"C:\Users\Test\docling\tests\data\pdf\04_KBank_ครั้งที่ 113.pdf"

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


# ------------------------------
# FUNCTION
# ------------------------------
def generate_keywords_from_filename(filename):
    base = os.path.basename(filename)
    name, _ = os.path.splitext(base)
    return [word for word in re.split(r"[\s._-]+", name) if len(word) > 1]


def ocr_pdf_tesseract(path):
    pdf = pdfium.PdfDocument(path)
    num_pages = len(pdf)
    full_text = ""

    print(f"📄 PDF มี {num_pages} หน้า กำลัง OCR ด้วย Tesseract ...")

    for i in range(num_pages):
        page = pdf.get_page(i)

        # ⚠️ API ใหม่ของ pypdfium2
        bitmap = page.render(scale=3)      # ⇒ ได้ PdfBitmap
        pil_image = bitmap.to_pil()        # ⇒ แปลงเป็น PIL Image

        # OCR
        page_text = pytesseract.image_to_string(pil_image, lang="tha+eng")

        print(f"✔ หน้า {i+1}: OCR {'สำเร็จ' if page_text.strip() else 'ว่าง'}")

        full_text += page_text + "\n"

    pdf.close()
    return full_text


def search_keywords(text, keywords):
    text_lower = text.lower()
    return {kw: kw.lower() in text_lower for kw in keywords}


# ------------------------------
# MAIN
# ------------------------------
if not os.path.exists(pdf_path):
    print("❌ ไม่พบไฟล์:", pdf_path)
    exit()

keywords = generate_keywords_from_filename(pdf_path)
print("🔍 Keywords จากชื่อไฟล์:", keywords)

text = ocr_pdf_tesseract(pdf_path)

if not text.strip():
    print("❌ OCR ไม่สามารถอ่านไฟล์นี้ได้เลย")
else:
    print(f"\n📌 OCR Extracted Text Length: {len(text)} characters\n")

    results = search_keywords(text, keywords)
# กรองเฉพาะ keywords ที่ไม่ใช่ตัวเลขล้วน
valid_keywords = [kw for kw in keywords if not kw.isdigit()]

if not valid_keywords:
    print("FAIL")   # ไม่มีคำให้ตรวจ เช่นมีแต่ตัวเลข
    exit()

results = search_keywords(text, valid_keywords)

# พบอย่างน้อยหนึ่งคำที่ไม่ใช่ตัวเลข = PASS
if any(results.values()):
    print(f"📄 ชื่อไฟล์:PASS")
else:
    print("FAIL")