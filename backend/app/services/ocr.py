import os
import re
from pathlib import Path
from typing import Dict, Any, Optional
from PIL import Image
import pytesseract
from app.config import settings

# Configure pytesseract path for Windows / Linux
if os.path.exists(settings.TESSERACT_CMD):
    pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD

def extract_raw_text(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    text = ""
    
    if ext == ".pdf":
        # Try pdfplumber first
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                pages_text = [page.extract_text() or "" for page in pdf.pages]
                text = "\n".join(pages_text).strip()
        except Exception:
            text = ""
            
        # Fallback to PyMuPDF (fitz) if pdfplumber returns empty text
        if not text:
            try:
                import fitz
                doc = fitz.open(file_path)
                pages_text = [page.get_text() for page in doc]
                text = "\n".join(pages_text).strip()
            except Exception:
                text = ""
                
        # If still empty (e.g. scanned PDF), convert PDF pages to images & run Tesseract OCR
        if not text:
            try:
                import fitz
                doc = fitz.open(file_path)
                ocr_texts = []
                for page in doc:
                    pix = page.get_pixmap()
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    ocr_texts.append(pytesseract.image_to_string(img))
                text = "\n".join(ocr_texts).strip()
            except Exception as e:
                text = f"[OCR Error on PDF: {str(e)}]"
    else:
        # Standard image OCR (JPG, PNG, TIFF)
        try:
            img = Image.open(file_path)
            text = pytesseract.image_to_string(img).strip()
        except Exception as e:
            text = f"[OCR Error on Image: {str(e)}]"
            
    return text

def parse_structured_credentials(raw_text: str) -> Dict[str, Any]:
    """
    Extract key document fields (name, degree, cgpa, roll_number, year, university, company) from OCR text.
    """
    data: Dict[str, Any] = {
        "raw_text": raw_text,
        "name": None,
        "degree": None,
        "cgpa": None,
        "year": None,
        "roll_number": None,
        "university": None,
        "company": None
    }
    
    if not raw_text:
        return data
        
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    
    # 1. CGPA extraction (e.g. CGPA: 8.75 or 8.75/10 or Grade Point Average: 9.2)
    cgpa_match = re.search(r'(?:cgpa|gpa|score|grade point average)[\s:]*([0-9]\.[0-9]{1,2})', raw_text, re.IGNORECASE)
    if cgpa_match:
        try:
            data["cgpa"] = float(cgpa_match.group(1))
        except ValueError:
            pass
            
    # 2. Degree extraction (B.Tech, B.E., M.Tech, B.Sc, Master of Science, Bachelor of Technology, etc.)
    degree_patterns = [
        r'(Bachelor of Technology|B\.?\s*Tech|Bachelor of Engineering|B\.?\s*E|Master of Technology|M\.?\s*Tech|B\.?\s*Sc|M\.?\s*Sc|MBA|Ph\.?D)',
    ]
    for pattern in degree_patterns:
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if match:
            data["degree"] = match.group(1).strip()
            break
            
    # 3. Roll Number / Registration Number
    roll_match = re.search(r'(?:roll\s*(?:no|number)|reg\s*(?:no|number)|enrollment\s*no)[\s:]*([A-Z0-9\-\/]+)', raw_text, re.IGNORECASE)
    if roll_match:
        data["roll_number"] = roll_match.group(1).strip()
        
    # 4. Year of Passing / Completion
    year_match = re.search(r'\b(20[0-2][0-9]|19[8-9][0-9])\b', raw_text)
    if year_match:
        data["year"] = int(year_match.group(1))
        
    # 5. Name Heuristic (e.g., Name: John Doe or This is to certify that John Doe)
    name_match = re.search(r'(?:certify that|awarded to|name[\s:]+)([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})', raw_text, re.IGNORECASE)
    if name_match:
        data["name"] = name_match.group(1).strip()
        
    return data
