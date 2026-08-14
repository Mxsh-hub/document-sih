import os
import re
from pathlib import Path
from typing import Dict, Any
import numpy as np
from app.models.schemas import ForensicsReport

def run_forensics_analysis(file_path: Path) -> Dict[str, Any]:
    ext = file_path.suffix.lower()
    
    # Critical Rule: Forensics Agent MUST reject camera photos/non-PDF files
    if ext != ".pdf":
        return {
            "error": "Camera photos not supported for forensics",
            "skipped": True,
            "font_consistency_score": 0.0,
            "metadata_clean": False,
            "seal_detected": False,
            "tamper_probability": 1.0,
            "overall_score": 0.0
        }
        
    font_consistency_score = 0.95
    metadata_clean = True
    seal_detected = False
    tamper_probability = 0.05
    suspicious_tools = []
    
    # 1. Metadata Forensics Check
    try:
        import fitz
        doc = fitz.open(file_path)
        meta = doc.metadata or {}
        creator = (meta.get("creator") or "").lower()
        producer = (meta.get("producer") or "").lower()
        
        editing_tools = ["photoshop", "gimp", "canva", "pdfedit", "foxit phantom", "adobe illustrator"]
        for tool in editing_tools:
            if tool in creator or tool in producer:
                metadata_clean = False
                suspicious_tools.append(tool)
                tamper_probability += 0.35
                
        # 2. Circular Seal Detection using OpenCV Hough Circles
        for page_idx in range(min(len(doc), 3)):
            page = doc[page_idx]
            pix = page.get_pixmap()
            
            # Convert PyMuPDF pixmap to numpy array for OpenCV
            img_np = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, pix.n))
            if pix.n == 4:  # RGBA to BGR
                import cv2
                img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGBA2BGR)
            elif pix.n == 3:  # RGB to BGR
                import cv2
                img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
            else:
                img_bgr = None

            if img_bgr is not None:
                import cv2
                gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
                blurred = cv2.GaussianBlur(gray, (9, 9), 2)
                circles = cv2.HoughCircles(
                    blurred, 
                    cv2.HOUGH_GRADIENT, 
                    dp=1.2, 
                    minDist=50, 
                    param1=50, 
                    param2=30, 
                    minRadius=20, 
                    maxRadius=120
                )
                if circles is not None:
                    seal_detected = True
                    break

        doc.close()
    except Exception as e:
        # Graceful fallback if PDF parsing fails
        metadata_clean = True
        
    # 3. Font Consistency Check using pdfminer
    try:
        from pdfminer.high_level import extract_pages
        from pdfminer.layout import LTTextContainer, LTChar
        
        fonts_found = set()
        for page_layout in extract_pages(file_path):
            for element in page_layout:
                if isinstance(element, LTTextContainer):
                    for text_line in element:
                        for character in text_line:
                            if isinstance(character, LTChar):
                                fonts_found.add(character.fontname)
                                
        # Check font count & variations
        if len(fonts_found) > 6:
            font_consistency_score = 0.60
            tamper_probability += 0.20
        elif len(fonts_found) > 0:
            font_consistency_score = 0.92
    except Exception:
        font_consistency_score = 0.88

    # Calculate overall forensics score (0.0 to 1.0)
    overall_score = round(
        (font_consistency_score * 0.3) + 
        ((1.0 if metadata_clean else 0.2) * 0.3) + 
        ((1.0 if seal_detected else 0.7) * 0.2) + 
        ((1.0 - tamper_probability) * 0.2), 
        2
    )
    overall_score = max(0.0, min(1.0, overall_score))

    return {
        "font_consistency_score": font_consistency_score,
        "metadata_clean": metadata_clean,
        "seal_detected": seal_detected,
        "tamper_probability": round(tamper_probability, 2),
        "overall_score": overall_score,
        "details": {
            "suspicious_tools": suspicious_tools,
            "skipped": False
        }
    }
