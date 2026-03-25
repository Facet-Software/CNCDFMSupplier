#!/usr/bin/env python3
# parse_drawing.py
# Standalone engineering drawing PDF parser.
# Run:  python parse_drawing.py drawing.pdf
# Deps: pip install pdfplumber
#
# Extracts quoting-relevant data from the text layer of a drawing PDF:
#   - General tolerance table
#   - Individual inline tolerances with actual values
#   - Surface finish callouts
#   - Material
#   - Datum letters
#   - Process/finishing notes
#   - GD&T presence
#
# Always outputs valid JSON. Never crashes silently.

import re
import sys
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Standard tolerance defaults when the actual value is missing or
# template-truncated (e.g. Onshape's ".XX = ±.0-" where the last
# digit is a dash). These are ASME Y14.5 / industry defaults.
_DEFAULT_TOLERANCES = {
    1: 0.1,       # .X    = ±.1
    2: 0.01,      # .XX   = ±.01
    3: 0.005,     # .XXX  = ±.005
    4: 0.0005,    # .XXXX = ±.0005
}


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

def parse_drawing(filepath):
    filepath = Path(filepath)
    if not filepath.exists():
        return _error(f"File not found: {filepath}")
    if filepath.suffix.lower() != '.pdf':
        return _error(f"Not a PDF: {filepath.suffix}")

    try:
        import pdfplumber
    except ImportError:
        return _error("pdfplumber not installed — pip install pdfplumber")

    try:
        text = _extract_text(filepath, pdfplumber)
    except Exception as e:
        return _error(f"PDF read error: {e}")

    if not text:
        return {
            "source":               "image_based",
            "flag":                 "PDF has no text layer — re-export from CAD "
                                    "as vector PDF (not image/scan).",
            "raw_text":             "",
            "general_tolerances":   None,
            "tightest_general_tol": None,
            "inline_tolerances":    [],
            "hole_callouts":        [],
            "thread_callouts":      [],
            "gdt_frames":           [],
            "radii":                [],
            "surface_finish":       {"detected": False, "general": [], "individual": [], "notes": []},
            "material":             None,
            "datums":               [],
            "process_notes":        [],
            "has_gdt":              False,
            "dimension_count":      0,
            "confidence":           "none",
        }

    # Normalize European comma decimals in dimension contexts.
    # "Ø5,6" → "Ø5.6", "M5x0,8" → "M5x0.8", "↧12,5" → "↧12.5"
    # Does NOT touch comma-separated lists like "A, B, C" or "1, 2, 3"
    # because those have a space after the comma.
    text_norm = _normalize_commas(text)

    general_tol   = _extract_general_tolerances(text_norm)
    inline_tols   = _extract_inline_tolerances(text_norm)
    hole_callouts = _extract_hole_callouts(text_norm)
    thread_calls  = _extract_thread_callouts(text_norm)
    gdt_frames    = _extract_gdt_frames(text_norm)
    radii         = _extract_radii(text_norm)
    surface       = _extract_surface_finish(text_norm)
    material      = _extract_material(text_norm)
    datums        = _extract_datums(text_norm)
    process_notes = _extract_process_notes(text_norm)
    has_gdt       = bool(gdt_frames) or _detect_gdt(text_norm)
    dim_count     = _count_dimensions(text_norm)

    # Tightest from numeric tiers only (skip 'fractional', 'angular_deg')
    numeric_tols = [v for k, v in (general_tol or {}).items()
                    if isinstance(k, int) and isinstance(v, (int, float))]
    tightest = min(numeric_tols) if numeric_tols else None

    flags = []
    if not general_tol:
        flags.append("No standard tolerance block found")
    if has_gdt and not gdt_frames:
        flags.append("GD&T detected but frames not fully extracted — "
                      "LLM parsing recommended")
    if dim_count == 0:
        flags.append("No dimensions found in text")

    confidence = "high" if general_tol and dim_count > 0 \
        else "medium" if general_tol or inline_tols \
        else "low"

    return {
        "source":               "text_layer",
        "flag":                 "; ".join(flags) if flags else None,
        "raw_text":             text,
        "general_tolerances":   general_tol,
        "tightest_general_tol": tightest,
        "inline_tolerances":    inline_tols,
        "hole_callouts":        hole_callouts,
        "thread_callouts":      thread_calls,
        "gdt_frames":           gdt_frames,
        "radii":                radii,
        "surface_finish":       surface,
        "material":             material,
        "datums":               datums,
        "process_notes":        process_notes,
        "has_gdt":              has_gdt,
        "dimension_count":      dim_count,
        "confidence":           confidence,
    }


# ---------------------------------------------------------------------------
# TEXT EXTRACTION
# ---------------------------------------------------------------------------

def _extract_text(filepath, pdfplumber):
    # Suppress pdfplumber/pdfminer internal debug logging
    for name in ['pdfplumber', 'pdfminer']:
        logging.getLogger(name).setLevel(logging.WARNING)

    pages = []
    with pdfplumber.open(str(filepath)) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                pages.append(t)
    return "\n".join(pages).strip()


def _normalize_commas(text):
    """
    Convert European comma decimals to periods in dimension contexts.

    Ø5,6 → Ø5.6     (diameter)
    ↧12,5 → ↧12.5   (depth)
    M5x0,8 → M5x0.8 (thread pitch)
    R2,5 → R2.5      (radius)

    Does NOT touch: "A, B, C" (space after comma) or prose text.
    Rule: a comma between two digits with no space on either side is
    a decimal separator, not a list separator.
    """
    # Replace digit,digit (no spaces) with digit.digit
    return re.sub(r'(\d),(\d)', r'\1.\2', text)


# ---------------------------------------------------------------------------
# GENERAL TOLERANCE TABLE
# ---------------------------------------------------------------------------

def _extract_general_tolerances(text):
    """
    Handles:
      .XX = +-.01          standard
      .XX = +-.0-          Onshape template (trailing dash = incomplete)
      TWO PLACE DECIMAL    +-.01
      DECIMALS .XX +-.010
      ISO 2768-m
      FRACTIONAL +-1/16
      ANGULAR +-1 deg
    """
    tiers = {}

    # .X+ = +-value (possibly incomplete with trailing dash)
    for m in re.finditer(
        r'\.(X+)\s*[:=]\s*[^\S\n]*[±+\-]+\s*\.?(\d+)',
        text, re.IGNORECASE
    ):
        dp = len(m.group(1))
        raw_digits = m.group(2)
        val = float('0.' + raw_digits)
        # If value is 0.0 or has fewer significant digits than the tier
        # implies, the text extraction truncated it. Use industry default.
        if val == 0.0 or len(raw_digits) < dp:
            val = _DEFAULT_TOLERANCES.get(dp, val)
        tiers[dp] = val

    # N PLACE DECIMAL +-value
    words = {'ONE': 1, 'TWO': 2, 'THREE': 3, 'FOUR': 4,
             '1': 1, '2': 2, '3': 3, '4': 4}
    for m in re.finditer(
        r'(\w+)[\s-]*PLACE\s+DECIMAL\s*[±+\-]+\s*\.?(\d+)',
        text, re.IGNORECASE
    ):
        w = m.group(1).upper()
        if w in words:
            dp = words[w]
            val = float('0.' + m.group(2))
            if val == 0.0:
                val = _DEFAULT_TOLERANCES.get(dp, val)
            tiers[dp] = val

    # DECIMALS .XX +-value
    for m in re.finditer(
        r'DECIMALS?\s*\.(X+)\s*[±+\-]+\s*\.?(\d+)',
        text, re.IGNORECASE
    ):
        dp = len(m.group(1))
        val = float('0.' + m.group(2))
        if val == 0.0:
            val = _DEFAULT_TOLERANCES.get(dp, val)
        tiers[dp] = val

    # ISO 2768 class
    iso = re.search(r'ISO\s*2768[\s-]*([fmcv])', text, re.IGNORECASE)
    if iso and not tiers:
        cls = {'f': {1: 0.05, 2: 0.05, 3: 0.02},
               'm': {1: 0.1,  2: 0.1,  3: 0.05},
               'c': {1: 0.2,  2: 0.3,  3: 0.1},
               'v': {1: 0.5,  2: 0.5,  3: 0.2}}
        tiers = cls.get(iso.group(1).lower(), {})

    # FRACTIONAL +-N/D
    fm = re.search(r'FRACTIONAL\s*[±+\-]+\s*(\d+)/(\d+)', text, re.IGNORECASE)
    if fm:
        d = int(fm.group(2))
        if d > 0:
            tiers['fractional'] = round(int(fm.group(1)) / d, 4)

    # ANGULAR +-N deg
    am = re.search(r'ANGULAR\s*[±+\-]+\s*(\d+)', text, re.IGNORECASE)
    if am:
        tiers['angular_deg'] = int(am.group(1))

    return tiers if tiers else None


# ---------------------------------------------------------------------------
# INLINE TOLERANCES
# ---------------------------------------------------------------------------

def _extract_inline_tolerances(text):
    results = []
    seen = set()

    # Pre-strip part numbers that look like tolerances: 100-002670, 800-002670
    cleaned = re.sub(r'\b\d{3,}-\d{3,}\b', '', text)

    # symmetric: .650±.0001 or 8.00 ±.001
    # REQUIRE decimal point in nominal — an integer like "100" before ± is
    # almost certainly a part number fragment, not a dimensioned feature.
    for m in re.finditer(r'(\d*\.\d+)\s*[±+\-]\s*(\.?\d+)', cleaned):
        nom = float(m.group(1))
        raw_tol = m.group(2)
        tol = float(raw_tol) if '.' in raw_tol else float('0.' + raw_tol)
        if nom > 1000 or tol > 1.0 or tol == 0.0:
            continue
        # A bare single-digit integer ≥ 2 after ± (e.g. "1.0±8") is almost
        # always garbled pdfplumber text (a dimension concatenated with
        # a different number), not a real tolerance.  Real tolerances are
        # written as ".8" or "0.8", not just "8".
        if '.' not in raw_tol and len(raw_tol) == 1 and int(raw_tol) >= 2:
            continue
        raw = m.group(0)
        if raw not in seen:
            seen.add(raw)
            results.append({"nominal": nom, "plus": tol, "minus": tol,
                            "type": "symmetric", "raw": raw})

    # asymmetric: 12.50 +.002/-.001
    for m in re.finditer(r'(\d*\.\d+)\s*\+(\.?\d+)\s*/?\s*-(\.?\d+)', cleaned):
        nom = float(m.group(1))
        p_raw, m_raw = m.group(2), m.group(3)
        plus  = float(p_raw) if '.' in p_raw else float('0.' + p_raw)
        minus = float(m_raw) if '.' in m_raw else float('0.' + m_raw)
        if nom > 1000:
            continue
        raw = m.group(0)
        if raw not in seen:
            seen.add(raw)
            results.append({"nominal": nom, "plus": plus, "minus": minus,
                            "type": "asymmetric", "raw": raw})

    return results


# ---------------------------------------------------------------------------
# HOLE CALLOUTS
# ---------------------------------------------------------------------------

def _extract_hole_callouts(text):
    """
    Extract structured hole callouts from the drawing text.

    Handles Onshape/SolidWorks/NX patterns:
      Ø.315 THRU                     — through hole
      Ø.217 ↧.500                    — blind hole with depth (↧ = depth symbol)
      ⌴Ø.463 ↧.157 X2               — counterbore: ⌴ = counterbore symbol
      Ø.500 ⌵82°                     — countersink: ⌵ = countersink symbol
      Ø.250 THRU ⌴Ø.375 ↧.125       — through + counterbore
      2X Ø.250 THRU                  — quantity prefix
      Ø.450                          — plain diameter callout

    Unicode symbols used by CAD tools:
      Ø  = U+00D8 (diameter)
      ⌴  = U+2334 (counterbore)
      ⌵  = U+2335 (countersink)
      ↧  = U+21A7 (depth)

    Returns list of structured dicts.
    """
    results = []
    captured_spans = []  # (start, end) of each captured match

    def _overlap(m):
        """True if this match overlaps a previously captured span."""
        for s, e in captured_spans:
            if not (m.end() <= s or m.start() >= e):
                return True
        return False

    # Diameter symbol: Ø (U+00D8) or spelled out as "DIA"
    DIA = r'[Ø\u00d8]'
    # Depth symbol: ↧ (U+21A7) or spelled out
    DEPTH = r'[↧\u21a7]'
    # Counterbore symbol: ⌴ (U+2334) or ⎕ or spelled out
    CBORE = r'[⌴\u2334\u2395]|(?:C\'?BORE)'
    # Countersink symbol: ⌵ (U+2335) or spelled out
    CSINK = r'[⌵\u2335]|(?:C\'?SINK|CSK)'

    # Pattern 1: Through hole — Ø.315 THRU  (optional quantity prefix)
    for m in re.finditer(
        rf'(?:(\d+)\s*X\s+)?{DIA}\s*(\d*\.?\d+)\s+THRU',
        text, re.IGNORECASE
    ):
        raw = m.group(0)
        if _overlap(m):
            continue
        captured_spans.append((m.start(), m.end()))
        qty = int(m.group(1)) if m.group(1) else 1
        results.append({
            "type": "through",
            "diameter": float(m.group(2)),
            "depth": None,
            "quantity": qty,
            "counterbore": None,
            "countersink": None,
            "raw": raw,
        })

    # Pattern 2: Through + counterbore — Ø.315 THRU ⌴Ø.463 ↧.157
    for m in re.finditer(
        rf'(?:(\d+)\s*X\s+)?{DIA}\s*(\d*\.?\d+)\s+THRU\s+(?:{CBORE})\s*{DIA}?\s*(\d*\.?\d+)\s*{DEPTH}\s*(\d*\.?\d+)',
        text, re.IGNORECASE
    ):
        raw = m.group(0)
        if _overlap(m):
            continue
        captured_spans.append((m.start(), m.end()))
        qty = int(m.group(1)) if m.group(1) else 1
        results.append({
            "type": "through_counterbore",
            "diameter": float(m.group(2)),
            "depth": None,
            "quantity": qty,
            "counterbore": {"diameter": float(m.group(3)), "depth": float(m.group(4))},
            "countersink": None,
            "raw": raw,
        })

    # Pattern 3: Counterbore without explicit THRU — ⌴Ø.463 ↧.157 X2
    for m in re.finditer(
        rf'(?:{CBORE})\s*{DIA}?\s*(\d*\.?\d+)\s*{DEPTH}\s*(\d*\.?\d+)(?:\s+X\s*(\d+))?',
        text, re.IGNORECASE
    ):
        raw = m.group(0)
        if _overlap(m):
            continue
        captured_spans.append((m.start(), m.end()))
        qty = int(m.group(3)) if m.group(3) else 1
        results.append({
            "type": "counterbore",
            "diameter": float(m.group(1)),
            "depth": float(m.group(2)),
            "quantity": qty,
            "counterbore": {"diameter": float(m.group(1)), "depth": float(m.group(2))},
            "countersink": None,
            "raw": raw,
        })

    # Pattern 4: Blind hole with depth — Ø.217 ↧.500
    for m in re.finditer(
        rf'(?:(\d+)\s*X\s+)?{DIA}\s*(\d*\.?\d+)\s*{DEPTH}\s*(\d*\.?\d+)',
        text, re.IGNORECASE
    ):
        raw = m.group(0)
        if _overlap(m):
            continue
        captured_spans.append((m.start(), m.end()))
        qty = int(m.group(1)) if m.group(1) else 1
        results.append({
            "type": "blind",
            "diameter": float(m.group(2)),
            "depth": float(m.group(3)),
            "quantity": qty,
            "counterbore": None,
            "countersink": None,
            "raw": raw,
        })

    # Pattern 5: Countersink — Ø.500 ⌵82° or CSK 82°
    for m in re.finditer(
        rf'(?:(\d+)\s*X\s+)?{DIA}\s*(\d*\.?\d+)\s+(?:{CSINK})\s*(\d+)\s*°?',
        text, re.IGNORECASE
    ):
        raw = m.group(0)
        if _overlap(m):
            continue
        captured_spans.append((m.start(), m.end()))
        qty = int(m.group(1)) if m.group(1) else 1
        results.append({
            "type": "countersink",
            "diameter": float(m.group(2)),
            "depth": None,
            "quantity": qty,
            "counterbore": None,
            "countersink": {"angle_deg": int(m.group(3))},
            "raw": raw,
        })

    # Pattern 6: Plain diameter — Ø.450 (no THRU, no depth)
    # Only match if not already captured by a more specific pattern above
    for m in re.finditer(
        rf'(?:(\d+)\s*X\s+)?{DIA}\s*(\d*\.?\d+)(?:\s|$|\n)',
        text
    ):
        raw = m.group(0).strip()
        if _overlap(m):
            continue
        captured_spans.append((m.start(), m.end()))
        qty = int(m.group(1)) if m.group(1) else 1
        results.append({
            "type": "diameter",
            "diameter": float(m.group(2)),
            "depth": None,
            "quantity": qty,
            "counterbore": None,
            "countersink": None,
            "raw": raw,
        })

    return results


# ---------------------------------------------------------------------------
# GD&T FEATURE CONTROL FRAMES
# ---------------------------------------------------------------------------

def _extract_gdt_frames(text):
    """
    Extract structured GD&T feature control frames from the text layer.

    Common text-layer representations (Onshape, SolidWorks):
      ⌖ 0.001 A B C        — position, ±0.001, datums A B C
      ⌖ Ø0.005 A B          — position, diametrical zone
      ⏥ 0.002 A             — flatness to datum A
      ⟂ 0.001 A             — perpendicularity
      ∥ 0.003 A B           — parallelism
      ◎ 0.002 A             — concentricity
      ⌯ 0.001 A             — symmetry / runout (depends on font)

    Unicode GD&T geometric characteristic symbols:
      ⌖ U+2316  position
      ⏥ U+23E5  flatness
      ⏤ U+23E4  straightness
      ○ U+25CB  circularity
      ◎ U+25CE  concentricity
      ⟂ U+27C2  perpendicularity
      ∥ U+2225  parallelism
      ⌯ U+232F  runout / symmetry

    Returns list of structured dicts.
    """
    results = []

    # Map unicode symbols to GD&T type names
    _SYMBOL_MAP = {
        '\u2316': 'position',
        '\u23e5': 'flatness',
        '\u23e4': 'straightness',
        '\u25cb': 'circularity',
        '\u25ce': 'concentricity',
        '\u27c2': 'perpendicularity',
        '\u2225': 'parallelism',
        '\u232f': 'runout',
        '\u2315': 'profile',         # ⌕
        '\u23e6': 'cylindricity',
        '\u232b': 'total_runout',     # ⬫ (font-dependent)
        '\u2313': 'profile_of_surface',  # ⌓
    }

    # Build a regex character class from all known symbols
    sym_chars = ''.join(_SYMBOL_MAP.keys())

    # Pattern: GD&T symbol + optional Ø + tolerance value + optional datum letters
    # e.g. ⌖ 0.001 A B C  or  ⌖ Ø0.005 A B  or  ⌖Ø.002 A
    # CRITICAL: datum capture must NOT cross newlines — adjacent text on the
    # next line (e.g. "Ra 1.6") would be falsely captured as datum letters.
    DIA = r'[Ø\u00d8]'
    for m in re.finditer(
        rf'([{sym_chars}])[^\S\n]*{DIA}?[^\S\n]*(\.?\d+\.?\d*)[^\S\n]*((?:[A-Z][^\S\n]*)*)',
        text
    ):
        sym = m.group(1)
        tol_val = float(m.group(2))
        datum_text = m.group(3).strip()
        # Deduplicate while preserving order
        seen_datums = set()
        datum_refs = []
        for L in re.findall(r'[A-Z]', datum_text):
            if L not in ('X', 'O') and L not in seen_datums:
                seen_datums.add(L)
                datum_refs.append(L)

        gdt_type = _SYMBOL_MAP.get(sym, 'unknown')

        results.append({
            "type":         gdt_type,
            "symbol":       sym,
            "tolerance":    tol_val,
            "diametrical":  bool(re.search(rf'{DIA}', m.group(0)[:3])),
            "datum_refs":   datum_refs,
            "raw":          m.group(0).strip(),
        })

    # Also try keyword-based extraction for cases where symbols didn't
    # come through as unicode (custom fonts render as garbage):
    # "TRUE POSITION 0.005 A B C" etc.
    _KEYWORD_MAP = {
        r'TRUE\s+POSITION':   'position',
        r'FLATNESS':          'flatness',
        r'PERPENDICULARITY':  'perpendicularity',
        r'PARALLELISM':       'parallelism',
        r'CONCENTRICITY':     'concentricity',
        r'CYLINDRICITY':      'cylindricity',
        r'STRAIGHTNESS':      'straightness',
        r'CIRCULAR\s+RUNOUT': 'circular_runout',
        r'TOTAL\s+RUNOUT':    'total_runout',
        r'PROFILE\s+OF\s+(?:A\s+)?SURFACE': 'profile_of_surface',
        r'PROFILE\s+OF\s+(?:A\s+)?LINE':    'profile_of_line',
        r'ANGULARITY':        'angularity',
    }

    for kw_pat, gdt_type in _KEYWORD_MAP.items():
        for m in re.finditer(
            rf'({kw_pat})\s+(\.?\d+\.?\d*)[^\S\n]*((?:[A-Z][^\S\n]*)*)',
            text, re.IGNORECASE
        ):
            tol_val = float(m.group(2))
            datum_text = m.group(3).strip()
            seen_datums = set()
            datum_refs = []
            for L in re.findall(r'[A-Z]', datum_text):
                if L not in ('X', 'O') and L not in seen_datums:
                    seen_datums.add(L)
                    datum_refs.append(L)
            # Skip if we already captured this via unicode symbol
            already = any(r['type'] == gdt_type and abs(r['tolerance'] - tol_val) < 1e-6
                          for r in results)
            if not already:
                results.append({
                    "type":         gdt_type,
                    "symbol":       None,
                    "tolerance":    tol_val,
                    "diametrical":  False,
                    "datum_refs":   datum_refs,
                    "raw":          m.group(0).strip(),
                })

    # Filter out false positives:
    # - Tolerance > 0.050" / 1.0mm is almost certainly a dimension, not a GD&T value
    # - Position/perpendicularity/parallelism/angularity REQUIRE datum references;
    #   if none found, the "frame" is probably a symbol next to an unrelated number
    _REQUIRES_DATUMS = {'position', 'perpendicularity', 'parallelism', 'angularity',
                        'concentricity', 'circular_runout', 'total_runout'}
    filtered = []
    for r in results:
        if r['tolerance'] > 0.1:
            continue  # tolerance zone > 0.1 is almost never real GD&T
        if r['type'] in _REQUIRES_DATUMS and not r['datum_refs']:
            continue  # these tolerance types always reference datums
        filtered.append(r)

    # --- Rescue pass ---
    # When pdfplumber fragments a GD&T frame across lines (e.g. the symbol is
    # on one line and the tolerance value is on the next, mixed with dimension
    # text), the main regex may grab a dimension as the tolerance and get
    # filtered out.  For each symbol in the text whose type does NOT appear in
    # `filtered`, search a window after the symbol for a small value (≤0.1)
    # that looks like the real tolerance zone.
    captured_types = {r['type'] for r in filtered}
    for m_sym in re.finditer(rf'[{sym_chars}]', text):
        sym = m_sym.group(0)
        gdt_type = _SYMBOL_MAP.get(sym)
        if not gdt_type or gdt_type in captured_types:
            continue
        # Search in a 120-char window after the symbol for a tolerance value
        window = text[m_sym.end():m_sym.end() + 120]
        # Look for small decimal numbers that look like GD&T zones
        for m_val in re.finditer(
            r'(?<![Ø\u00d8\d])(\d?\.\d{2,5})(?:\s+|\s*\n\s*)((?:[A-Z](?:\s+[A-Z]){0,2})?)',
            window
        ):
            tol_val = float(m_val.group(1))
            if tol_val > 0.1 or tol_val < 1e-6:
                continue
            datum_text = m_val.group(2).strip()
            seen_d = set()
            datum_refs = []
            for L in re.findall(r'[A-Z]', datum_text):
                if L not in ('X', 'O') and L not in seen_d:
                    seen_d.add(L)
                    datum_refs.append(L)
            if gdt_type in _REQUIRES_DATUMS and not datum_refs:
                continue
            filtered.append({
                "type":         gdt_type,
                "symbol":       sym,
                "tolerance":    tol_val,
                "diametrical":  False,
                "datum_refs":   datum_refs,
                "raw":          f"{sym} {m_val.group(0).strip()}",
            })
            captured_types.add(gdt_type)
            break  # one rescue per symbol type

    return filtered


# ---------------------------------------------------------------------------
# RADIUS CALLOUTS
# ---------------------------------------------------------------------------

def _extract_radii(text):
    """
    Extract radius callouts: R.010 TYP, R.250, R.125, etc.

    Returns list of {value, is_typical, raw}.
    """
    results = []
    seen = set()

    for m in re.finditer(r'R\s*(\d*\.\d+)\s*(TYP)?', text, re.IGNORECASE):
        val = float(m.group(1))
        raw = m.group(0).strip()
        if raw in seen or val > 100:  # filter unreasonable values
            continue
        seen.add(raw)
        results.append({
            "value":      val,
            "is_typical": bool(m.group(2)),
            "raw":        raw,
        })

    return results


# ---------------------------------------------------------------------------
# THREAD CALLOUTS
# ---------------------------------------------------------------------------

def _extract_thread_callouts(text):
    """
    Extract thread callouts from the drawing text.

    Handles:
      M5x0.8 ↧12          — metric thread with pitch and depth
      M5x0.8               — metric thread with pitch
      M5 ↧12               — metric thread with depth (standard pitch)
      M5                    — metric thread (standard pitch)
      1/4-20 UNC            — imperial thread
      #10-32 UNF ↧.500     — imperial with depth
      3/8-16 UNC THRU       — imperial through

    Returns list of structured dicts.
    """
    results = []
    seen = set()

    DIA = r'[Ø\u00d8]'
    DEPTH = r'[↧\u21a7]'

    # Metric: M5x0.8 ↧12  or  M5x0.8  or  M5 ↧12
    for m in re.finditer(
        rf'(M\d+(?:\.\d+)?)\s*(?:x\s*(\d+\.?\d*))?\s*(?:{DEPTH}\s*(\d+\.?\d*))?\s*(THRU)?',
        text, re.IGNORECASE
    ):
        raw = m.group(0).strip()
        if raw in seen or len(raw) < 2:
            continue
        # Must have at least the M designation
        if not m.group(1):
            continue
        seen.add(raw)
        results.append({
            "designation": m.group(1),
            "pitch":       float(m.group(2)) if m.group(2) else None,
            "depth":       float(m.group(3)) if m.group(3) else None,
            "through":     bool(m.group(4)),
            "system":      "metric",
            "raw":         raw,
        })

    # Imperial: 1/4-20 UNC or #10-32 UNF ↧.500 THRU
    for m in re.finditer(
        rf'((?:\d+/\d+|\#\d+)\s*-\s*\d+)\s*(UNC|UNF|UNEF)?\s*(?:{DEPTH}\s*(\d*\.?\d+))?\s*(THRU)?',
        text, re.IGNORECASE
    ):
        raw = m.group(0).strip()
        if raw in seen:
            continue
        seen.add(raw)
        results.append({
            "designation": m.group(1).strip(),
            "pitch":       None,
            "depth":       float(m.group(3)) if m.group(3) else None,
            "through":     bool(m.group(4)),
            "system":      "imperial",
            "class":       m.group(2).upper() if m.group(2) else None,
            "raw":         raw,
        })

    return results


# ---------------------------------------------------------------------------
# SURFACE FINISH
# ---------------------------------------------------------------------------

def _extract_surface_finish(text):
    """
    Detect surface finish callouts, distinguishing between:
      - general: applies to all surfaces (from title block or general note)
      - individual: applies to specific surfaces (standalone callouts)

    General examples: "ALL SURFACES 125 RMS", "SURFACE FINISH: 63"
    Individual examples: bare "0.8" on a drawing view, "Ra 1.6" on a leader
    """
    general_values = []
    individual_values = []
    notes = []

    # General surface finish notes — "ALL SURFACES 125 RMS" etc.
    for pat in [r'ALL\s+SURFACES?\s+(\d+\.?\d*)\s*(?:RMS|Ra|[µu]in)',
                r'SURFACE\s+FINISH\s*[:=]\s*(\d+\.?\d*)']:
        for m in re.finditer(pat, text, re.IGNORECASE):
            general_values.append(float(m.group(1)))
            notes.append(m.group(0).strip())

    # General note reference (no value extracted, just flagged)
    for m in re.finditer(r'UNLESS\s+OTHERWISE\s+SPECIFIED.*(?:FINISH|SURFACE)', text, re.IGNORECASE):
        notes.append(m.group(0).strip())

    # Explicit Ra with label: "Ra 1.6" or "1.6 Ra" — individual callout
    # UNLESS it appears on a line with titleblock keywords (MATERIAL, FINISH,
    # etc.), in which case it's the general surface finish from the titleblock.
    _TITLEBLOCK_CONTEXT = re.compile(
        r'(?:MATERIAL|FINISH|SURFACE|TITLE|SIZE|SCALE|DWG|WEIGHT|SHEET'
        r'|6061|7075|2024|303|304|316|ALUMINUM|ALUMINIUM|STEEL|BRASS|TITANIUM'
        r'|INCONEL|DELRIN|PEEK|COPPER|BRONZE)',
        re.IGNORECASE
    )
    for m in re.finditer(r'Ra\s*(\d+\.?\d*)', text, re.IGNORECASE):
        val = float(m.group(1))
        if val > 50:  # no standard Ra value exceeds ~50 µm
            continue
        # Find the line this match is on
        line_start = text.rfind('\n', 0, m.start()) + 1
        line_end = text.find('\n', m.end())
        if line_end == -1:
            line_end = len(text)
        line = text[line_start:line_end]
        if _TITLEBLOCK_CONTEXT.search(line):
            general_values.append(val)
        else:
            individual_values.append(val)
    for m in re.finditer(r'(\d+\.?\d*)\s*Ra\b', text, re.IGNORECASE):
        val = float(m.group(1))
        if val > 50:  # filter out material numbers like "6061 Ra"
            continue
        line_start = text.rfind('\n', 0, m.start()) + 1
        line_end = text.find('\n', m.end())
        if line_end == -1:
            line_end = len(text)
        line = text[line_start:line_end]
        if _TITLEBLOCK_CONTEXT.search(line):
            general_values.append(val)
        else:
            individual_values.append(val)

    # RMS with label: "125 RMS" — could be general or individual depending
    # on context, but if not already captured by general patterns above,
    # treat as individual
    for m in re.finditer(r'(\d+)\s*RMS', text, re.IGNORECASE):
        val = float(m.group(1))
        if val not in general_values:
            individual_values.append(val)

    # Microinch with label: "63 µin"
    for m in re.finditer(r'(\d+)\s*[µu]in', text, re.IGNORECASE):
        individual_values.append(float(m.group(1)))

    # Bare standard Ra values on their own line — individual surface callout
    standard_ra_um = {0.1, 0.2, 0.4, 0.8, 1.6, 3.2, 6.3, 12.5, 25.0, 50.0}
    for m in re.finditer(r'(?:^|\n)\s*(\d+\.?\d*)\s*(?:$|\n)', text):
        val = float(m.group(1))
        if val in standard_ra_um:
            individual_values.append(val)

    general_values = sorted(set(general_values))
    individual_values = sorted(set(individual_values))

    return {
        "detected":    bool(general_values or individual_values or notes),
        "general":     general_values,
        "individual":  individual_values,
        "notes":       notes,
    }


# ---------------------------------------------------------------------------
# MATERIAL
# ---------------------------------------------------------------------------

def _extract_material(text):
    """
    Extract material callout. Search order:
      1. Common alloys (CAST IRON, 6061-T6, etc.) — most reliable
      2. Spec numbers (AMS, ASTM, etc.)
      3. Labeled field (MATERIAL: value) — riskiest, title block layout varies
    """
    # Known title block field labels that are NOT materials
    _FIELD_LABELS = {'FINISH', 'TITLE', 'SIZE', 'DRAWN', 'CHECKED', 'APPROVED',
                     'SCALE', 'WEIGHT', 'SHEET', 'DATE', 'NAME', 'REV',
                     'DWG', 'ITEM', 'SURFACE', 'NOTES', 'UNLESS'}

    # 1. Common alloys — match these first, they're unambiguous
    for pat in [r'\b(CAST\s*IRON)\b', r'\b(DUCTILE\s*IRON)\b',
                r'\b(6061[\s-]*T6(?:51)?)\b', r'\b(7075[\s-]*T6(?:51)?)\b',
                r'\b(2024[\s-]*T\d+)\b',
                r'\b(ALUMINU?M\s*\d{4}(?:[\s-]*T\d+)?)\b',  # Aluminum 6061, Aluminium 7075-T6
                r'\b(303\s*(?:SS|STAINLESS))\b',
                r'\b(304L?\s*(?:SS|STAINLESS)?)\b', r'\b(316L?\s*(?:SS|STAINLESS)?)\b',
                r'\b(17[\s-]*4\s*(?:PH)?)\b', r'\b(INCONEL\s*\d+)\b',
                r'\b(Ti[\s-]*6Al[\s-]*4V)\b', r'\b(TITANIUM\s*(?:GRADE)?\s*\d*)\b',
                r'\b(DELRIN|PEEK|ULTEM|VESPEL|TORLON|NYLON|ACETAL)\b',
                r'\b(BRASS\s*\d*)\b', r'\b(COPPER\s*\d*)\b', r'\b(BRONZE\s*\d*)\b',
                r'\b(TOOL\s*STEEL)\b', r'\b(STAINLESS\s*STEEL(?:\s*\d{3}L?)?)\b',
                r'\b(MILD\s*STEEL)\b', r'\b(ALUMINU?M)\b']:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()

    # 2. Spec numbers: AMS, ASTM, SAE, MIL, QQ
    for m in re.finditer(
        r'((?:AMS|ASTM|SAE|MIL|QQ)\s*[A-Z]?\s*\d{3,6}[A-Z]?)',
        text, re.IGNORECASE
    ):
        return m.group(1).strip()

    # 3. Labeled: MATERIAL: value (stop at newline or next field)
    for m in re.finditer(
        r"(?:MATERIAL|MAT'?L|MATL)\s*[:=]?\s*([A-Z0-9][A-Z0-9\s\-/\.]{2,40})",
        text, re.IGNORECASE
    ):
        mat = m.group(1).strip().split('\n')[0].strip()
        mat = re.split(
            r'\s+(?:FINISH|SURFACE|HEAT|TREAT|SCALE|DRAWN|UNLESS|TITLE|SIZE|DWG|ITEM)',
            mat, flags=re.IGNORECASE
        )[0].strip()
        # Reject if the extracted value is itself a field label
        if mat.upper() in _FIELD_LABELS:
            continue
        if len(mat) >= 3:
            return mat

    # 4. MATERIAL label with value on next line
    for m in re.finditer(
        r'MATERIAL\s*\n\s*([A-Z][A-Z0-9\s\-/\.]{2,30})',
        text, re.IGNORECASE
    ):
        mat = m.group(1).strip().split('\n')[0].strip()
        if mat.upper() not in _FIELD_LABELS:
            return mat

    return None


# ---------------------------------------------------------------------------
# DATUMS
# ---------------------------------------------------------------------------

def _extract_datums(text):
    datums = set()

    # Explicit: DATUM A
    for m in re.finditer(r'DATUM\s+([A-Z])\b', text, re.IGNORECASE):
        datums.add(m.group(1).upper())

    # Target: -A-
    for m in re.finditer(r'-([A-Z])-', text):
        if m.group(1) not in ('X', 'O'):
            datums.add(m.group(1))

    # Bars: |A|
    for m in re.finditer(r'\|([A-Z])\|', text):
        datums.add(m.group(1))

    # GD&T frame context: tolerance value (3+ decimal places) followed by
    # space-separated single letters. Real GD&T is always .001+ precision.
    # This filters out things like "0.744 LB" (weight) or "0.625 in" (unit).
    # Also require at least 2 letters to distinguish from random text.
    for m in re.finditer(
        r'0?\.\d{3,5}\s+([A-Z](?:\s+[A-Z]){1,2})(?:\s|$|\n)',
        text
    ):
        for L in re.findall(r'[A-Z]', m.group(1)):
            datums.add(L)

    # Boxed: [A] or (A) — but not common words in parens
    for m in re.finditer(r'[\[\(]([A-Z])[\]\)]', text):
        if m.group(1) not in ('X', 'O'):
            datums.add(m.group(1))

    return sorted(datums)


# ---------------------------------------------------------------------------
# PROCESS NOTES
# ---------------------------------------------------------------------------

def _extract_process_notes(text):
    # Match the note pattern, then truncate at known title block labels
    # that pdfplumber may concatenate onto the same line.
    _TITLE_BLOCK_LABELS = (
        r'\s+(?:SIZE|ITEM\s*NO|DWG\s*NO|REV\b|SCALE|WEIGHT|SHEET|DATE|NAME'
        r'|DRAWN|CHECKED|APPROVED|TITLE|FINISH|MATERIAL|SURFACE'
        r'|Revision|DETAILS|ENGINEERING|THIRD\s+ANGLE|DO\s+NOT\s+SCALE'
        r'|UNLESS\s+OTHERWISE\s+SPECIFIED|DIMENSIONS\s+ARE)'
    )

    patterns = [
        (r'DEBURR\s+(?:ALL\s+)?(?:EDGES|SHARP\s+EDGES)[^\n]*',       "deburr"),
        (r'BREAK\s+(?:ALL\s+)?(?:SHARP\s+)?EDGES?[^\n]*',            "edge_break"),
        (r'REMOVE\s+(?:ALL\s+)?BURRS[^\n]*',                          "deburr"),
        (r'(?:HARD|TYPE\s+III?)\s*ANODIZE[^\n]*',               "hard_anodize"),
        (r'ANODIZE[^\n]*(?:PER|MIL[\s-]*A[\s-]*8625)?[^\n]*',   "anodize"),
        (r'PASSIVAT(?:E|ION)[^\n]*',                             "passivate"),
        (r'(?:BLACK|CHEM(?:ICAL)?)\s*OXIDE[^\n]*',              "black_oxide"),
        (r'(?:ELECTRO(?:LESS)?[\s-]*)?NICKEL\s+PLAT(?:E|ING)[^\n]*', "nickel_plate"),
        (r'HEAT\s+TREAT[^\n]*',                                  "heat_treat"),
        (r'STRESS\s+RELIEV[^\n]*',                               "stress_relieve"),
        (r'BEAD\s+BLAST[^\n]*',                                  "bead_blast"),
        (r'TUMBLE[^\n]*',                                         "tumble"),
        (r'(?:CHEM[\s-]*FILM|CHROMATE|ALODINE|IRIDITE)[^\n]*',  "chem_film"),
        (r'(?:ITAR|EXPORT\s+CONTROLLED|EAR)[^\n]*',             "export_control"),
        (r'CERTIF(?:ICATE|ICATION)\s+(?:OF\s+)?(?:CONFORMANCE|COMPLIANCE)[^\n]*', "cert_required"),
        (r'FIRST\s+ARTICLE[^\n]*',                               "first_article"),
        (r'(?:MAGNETIC\s+PARTICLE|DYE\s+PENETRANT|X[\s-]*RAY|NDT|NDE)[^\n]*', "ndt"),
        (r'ALL\s+FILLETS?\s+AND\s+ROUNDS?\s+[\d\.]+[^\n]*',    "fillets_and_rounds"),
    ]

    seen = set()
    results = []
    for pat, cat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            if cat not in seen:
                seen.add(cat)
                raw = m.group(0).strip()
                # Truncate at any title block field label that got concatenated
                raw = re.split(_TITLE_BLOCK_LABELS, raw, maxsplit=1, flags=re.IGNORECASE)[0].strip()
                # Detect mid-sentence truncation at line break — pdfplumber
                # often splits notes that wrap across a titleblock boundary.
                if raw and re.search(r'\b(?:AND|OR|&)\s*$', raw, re.IGNORECASE):
                    raw = raw.rstrip() + ' …'
                if raw:
                    results.append({"category": cat, "text": raw[:80]})
    return results


# ---------------------------------------------------------------------------
# GD&T PRESENCE
# ---------------------------------------------------------------------------

def _detect_gdt(text):
    keywords = [
        r'-[A-Z]-', r'DATUM\s+[A-Z]\b', r'TRUE\s+POSITION',
        r'CONCENTRICIT', r'PERPENDICULAR', r'PARALLEL(?:ISM)?',
        r'FLATNESS', r'CYLINDRICIT', r'CIRCULAR\s+RUNOUT',
        r'TOTAL\s+RUNOUT', r'STRAIGHTNESS',
        r'PROFILE\s+OF\s+(?:A\s+)?(?:LINE|SURFACE)',
        r'ANGULARIT', r'\bMMC\b|\bLMC\b|\bRFS\b', r'BASIC\s+DIM',
    ]
    symbols = '\u2316\u232f\u2334\u232b\u23e4\u23e5\u25ce\u2225\u27c2\u2315\u23e6\u21a7'

    for pat in keywords:
        if re.search(pat, text, re.IGNORECASE):
            return True
    for s in symbols:
        if s in text:
            return True
    # Tolerance value + datum letters pattern: "0.001 A B C"
    if re.search(r'0?\.\d{3,5}\s+[A-Z]\s+[A-Z]', text):
        return True
    return False


# ---------------------------------------------------------------------------
# DIMENSION COUNT
# ---------------------------------------------------------------------------

def _count_dimensions(text):
    c = text
    c = re.sub(r'SCALE\s+\d+\s*:\s*\d+', '', c, flags=re.IGNORECASE)
    c = re.sub(r'\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}', '', c)
    c = re.sub(r'\b\d{3,}-\d{3,}\b', '', c)
    c = re.sub(r'REV\s*[A-Z0-9]+', '', c, flags=re.IGNORECASE)
    c = re.sub(r'SHEET\s*\d+\s*OF\s*\d+', '', c, flags=re.IGNORECASE)
    c = re.sub(r'DWG\s*(?:NO|#|NUM)?\s*[A-Z0-9\-]+', '', c, flags=re.IGNORECASE)
    c = re.sub(r'(?:DRAWN|CHECKED|APPROVED)\s+\w+', '', c, flags=re.IGNORECASE)
    # Count both decimal numbers (.315, 12.5) and standalone integers (84, 112)
    # that are likely dimensions. Filter out single digits (zone labels: 1-6)
    # and very large numbers (part numbers that survived cleanup).
    decimals = re.findall(r'\b\d*\.\d{1,5}\b', c)
    integers = re.findall(r'(?<![.\d])\b(\d{2,4})\b(?![.\d\-])', c)
    # Filter integers: must be in a plausible dimension range (1-9999)
    integers = [i for i in integers if 1 < int(i) < 10000]
    return len(decimals) + len(integers)


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _error(msg):
    return {
        "source": "error", "flag": msg, "raw_text": "",
        "general_tolerances": None, "tightest_general_tol": None,
        "inline_tolerances": [], "hole_callouts": [], "thread_callouts": [],
        "gdt_frames": [], "radii": [],
        "surface_finish": {"detected": False, "general": [], "individual": [], "notes": []},
        "material": None, "datums": [], "process_notes": [],
        "has_gdt": False, "dimension_count": 0, "confidence": "none",
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Only enable OUR logging, suppress pdfplumber/pdfminer noise
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")

    if len(sys.argv) < 2:
        print("Usage: python parse_drawing.py <drawing.pdf>")
        sys.exit(1)

    result = parse_drawing(sys.argv[1])

    output = {k: v for k, v in result.items() if k != "raw_text"}
    output["raw_text_chars"] = len(result.get("raw_text", ""))
    print(json.dumps(output, indent=2, default=str))