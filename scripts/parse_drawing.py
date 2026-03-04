import sys
import json
import os
import re
import pdfplumber
import fitz
import anthropic
import base64

# ──────────────────────────────────────────────────────────────────
# parse_drawing.py
# Extracts tolerances from engineering drawing PDFs.
#
# Flow:
#   1. pdfplumber text extraction (free, works for SolidWorks/Fusion)
#   2. If not, tell to put as PDF
#
# Called from api/jobs/create.ts via spawn, outputs JSON to stdout.
# Future: replace Claude Vision with proprietary trained model.
# ──────────────────────────────────────────────────────────────────

def extract_text_layer(path: str) -> str:
    """Extract text directly from PDF. Returns empty if image-based."""
    text = ""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""
    return text.strip()

def parse_drawing(path: str) -> dict:
    text = extract_text_layer(path)
    if text:
        return { "source": "text_layer", "raw": text }
    return { 
        "source": "no_text_layer", 
        "error": "PDF has no text layer. If using Onshape: File → Print → Save as PDF instead of Export." 
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({ "error": "No file path provided" }))
        sys.exit(1)
    try:
        result = parse_drawing(sys.argv[1])
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(json.dumps({ "error": str(e) }))
        sys.exit(1)