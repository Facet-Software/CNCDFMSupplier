import sys
import json
import re
import pdfplumber

# ──────────────────────────────────────────────────────────────────
# parse_drawing.py
# Extracts tolerances from engineering drawing PDFs.
#
# Flow:
#   1. pdfplumber extracts text layer (free)
#   2. If no text layer → flag as image-based, tell user to re-export
#   3. If text but no standard tolerance block → flag for manual review
#
# Called from api/jobs/create.ts via spawn, outputs JSON to stdout.
# Always returns valid JSON — never crashes silently.
# ──────────────────────────────────────────────────────────────────


def extract_text_layer(path):
    text = ""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""
    return text.strip()


def parse_general_tolerances(text):
    """Parse .XX = ±.00 format tolerance table. Returns {} if not found."""
    tiers = {}
    for match in re.finditer(r'\.(X+)\s*=\s*[±+\-]+\.?(0+)-?', text, re.IGNORECASE):
        x_count = len(match.group(1))
        tiers[x_count] = round(10 ** -x_count, x_count)
    return tiers


def count_by_tier(text, tiers):
    """Count dimensions in text by decimal place tier."""
    cleaned = re.sub(r'SCALE\s+\d+:\d+', '', text)
    cleaned = re.sub(r'\d{2}/\d{2}/\d{4}', '', cleaned)
    cleaned = re.sub(r'\b\d{3}-\d{6}\b', '', cleaned)
    counts = {}
    for num in re.findall(r'\b\d*\.\d+\b', cleaned):
        dp = len(num.split('.')[1])
        if dp in tiers:
            counts[dp] = counts.get(dp, 0) + 1
    return counts


def find_tightest(tiers, counts):
    """Return tightest tolerance tier that has at least one dimension."""
    for dp in sorted(tiers.keys(), reverse=True):
        if dp in counts:
            return tiers[dp], counts[dp]
    return None, 0


def has_inline_tolerance(text):
    return bool(re.search(r'\d\s*\u00b1\s*\.?\d', text))


def has_gdt(text):
    return any(sym in text for sym in ['\u2316', '\u232f', '\u2334', '\u232b'])


def parse_drawing(path):
    # step 1 — extract text
    text = extract_text_layer(path)

    if not text:
        return {
            "source": "image_based",
            "flag": "PDF has no text layer. If using Onshape: File > Print > Save as PDF instead of Export.",
            "tightest_general_tolerance": None,
            "tightest_tier_count": 0,
            "has_inline_tolerance": False,
            "has_gdt": False
        }

    # step 2 — parse tolerance table
    tiers = parse_general_tolerances(text)

    if not tiers:
        return {
            "source": "text_layer",
            "flag": "No standard tolerance block found — requires manual review.",
            "tightest_general_tolerance": None,
            "tightest_tier_count": 0,
            "has_inline_tolerance": has_inline_tolerance(text),
            "has_gdt": has_gdt(text)
        }

    # step 3 — count and resolve
    counts = count_by_tier(text, tiers)
    tightest, tightest_count = find_tightest(tiers, counts)

    return {
        "source": "text_layer",
        "flag": None,
        "general_tolerances": {str(k) + "_place": v for k, v in tiers.items()},
        "tightest_general_tolerance": tightest,
        "tightest_tier_count": tightest_count,
        "has_inline_tolerance": has_inline_tolerance(text),
        "has_gdt": has_gdt(text)
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No file path provided"}))
        sys.exit(1)
    try:
        result = parse_drawing(sys.argv[1])
        print(json.dumps(result, indent=2))
    except FileNotFoundError:
        print(json.dumps({"error": "File not found: " + sys.argv[1]}))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)