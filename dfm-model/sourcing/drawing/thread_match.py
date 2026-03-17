# sourcing/drawing/thread_match.py
# Maps thread callouts from a drawing PDF to hole profiles detected
# in the STEP geometry, using tap drill diameter as the matching key.
#
# A thread callout like "M5x0.8 ↧12" implies:
#   - Tap drill diameter = 5.0 - 0.8 = 4.2mm
#   - Thread depth = 12mm
# The STEP file shows a Ø4.2mm blind hole. This module finds that
# correspondence and annotates the hole profile with thread info.
#
# When a match is found, the hole's type is changed to "thread" and
# the thread designation, pitch, and class are attached.

import logging
import math

logger = logging.getLogger(__name__)

# Standard ISO metric coarse pitches (mm).
# Used when the drawing callout specifies M-size without pitch.
_METRIC_COARSE_PITCH = {
    1: 0.25, 1.2: 0.25, 1.4: 0.3, 1.6: 0.35, 1.8: 0.35,
    2: 0.4, 2.5: 0.45, 3: 0.5, 3.5: 0.6, 4: 0.7, 5: 0.8,
    6: 1.0, 7: 1.0, 8: 1.25, 10: 1.5, 12: 1.75,
    14: 2.0, 16: 2.0, 18: 2.5, 20: 2.5, 22: 2.5,
    24: 3.0, 27: 3.0, 30: 3.5, 33: 3.5, 36: 4.0,
}

# Common imperial thread tap drill diameters (inches).
# Format: "designation" → tap_drill_diameter_inches
_IMPERIAL_TAP_DRILLS = {
    "#0-80":   0.0469,  "#1-64":   0.0595,  "#1-72":   0.0595,
    "#2-56":   0.0700,  "#2-64":   0.0700,  "#3-48":   0.0785,
    "#4-40":   0.0890,  "#4-48":   0.0935,  "#5-40":   0.1015,
    "#5-44":   0.1040,  "#6-32":   0.1065,  "#6-40":   0.1130,
    "#8-32":   0.1360,  "#8-36":   0.1360,  "#10-24":  0.1495,
    "#10-32":  0.1590,  "#12-24":  0.1770,  "#12-28":  0.1820,
    "1/4-20":  0.2010,  "1/4-28":  0.2130,
    "5/16-18": 0.2570,  "5/16-24": 0.2720,
    "3/8-16":  0.3125,  "3/8-24":  0.3320,
    "7/16-14": 0.3680,  "7/16-20": 0.3906,
    "1/2-13":  0.4219,  "1/2-20":  0.4531,
    "9/16-12": 0.4844,  "9/16-18": 0.5156,
    "5/8-11":  0.5312,  "5/8-18":  0.5781,
    "3/4-10":  0.6562,  "3/4-16":  0.6875,
    "7/8-9":   0.7656,  "7/8-14":  0.8125,
    "1-8":     0.8750,  "1-12":    0.9219,
}


def match_threads_to_holes(thread_callouts, hole_profiles, display_unit='mm'):
    """
    Match drawing thread callouts to STEP hole profiles.

    For each thread callout, computes the expected tap drill diameter
    and searches hole_profiles for a matching hole. When found, mutates
    the hole profile in place:
      - hole_type → "thread"
      - thread_designation → "M5x0.8" or "1/4-20 UNC"
      - thread_pitch → 0.8 (mm) or None
      - thread_class → "UNC" / "UNF" / None

    Parameters
    ----------
    thread_callouts : list[dict]
        From parse_drawing() → thread_callouts.
    hole_profiles : list[dict]
        From the STEP pipeline (already classified).
    display_unit : str
        'mm' or 'inch' — affects matching tolerance.

    Returns
    -------
    list[dict] — match results for logging/reporting. Each entry:
        thread    : str  — designation
        hole_idx  : int  — index into hole_profiles, or None
        tap_drill : float — expected tap drill diameter (mm)
        matched   : bool
        confidence: str  — 'high', 'medium', 'low'
    """
    if not thread_callouts or not hole_profiles:
        return []

    results = []
    matched_hole_idxs = set()

    for tc in thread_callouts:
        designation = tc.get('designation', '')
        system = tc.get('system', 'metric')
        pitch = tc.get('pitch')
        depth_mm = tc.get('depth')

        # Compute expected tap drill diameter in mm
        tap_drill_mm = _compute_tap_drill(designation, pitch, system)
        if tap_drill_mm is None:
            results.append({
                'thread': designation,
                'hole_idx': None,
                'tap_drill_mm': None,
                'matched': False,
                'confidence': 'none',
                'reason': f'Cannot compute tap drill for {designation}',
            })
            continue

        # Convert drawing depth to mm if needed
        if depth_mm is not None and display_unit == 'inch':
            depth_mm = depth_mm * 25.4

        # Search hole profiles for a diameter match
        match = _find_best_match(
            tap_drill_mm, depth_mm, hole_profiles, matched_hole_idxs,
        )

        if match is not None:
            hi, confidence = match
            matched_hole_idxs.add(hi)

            # Mutate hole profile in place
            hp = hole_profiles[hi]
            hp['hole_type'] = 'thread'
            hp['thread_designation'] = designation
            if pitch:
                hp['thread_designation'] += f'x{pitch}'
            hp['thread_pitch'] = pitch
            hp['thread_class'] = tc.get('class')
            hp['thread_system'] = system

            logger.info(
                f"  Thread match: {designation} → hole {hi} "
                f"(tap_drill={tap_drill_mm:.2f}mm, "
                f"hole_dia={hp['rep_radius_mm']*2:.2f}mm, "
                f"confidence={confidence})"
            )

            results.append({
                'thread': hp['thread_designation'],
                'hole_idx': hi,
                'tap_drill_mm': round(tap_drill_mm, 3),
                'matched': True,
                'confidence': confidence,
            })
        else:
            results.append({
                'thread': designation,
                'hole_idx': None,
                'tap_drill_mm': round(tap_drill_mm, 3),
                'matched': False,
                'confidence': 'none',
                'reason': f'No hole with diameter ~{tap_drill_mm:.2f}mm found',
            })

    return results


def _compute_tap_drill(designation, pitch, system):
    """
    Compute tap drill diameter in mm from thread designation.

    Metric: tap_drill = major_diameter - pitch
    Imperial: lookup table (drill charts are non-formulaic)
    """
    if system == 'metric':
        # Parse major diameter from "M5", "M10", "M2.5", etc.
        import re
        m = re.match(r'M(\d+\.?\d*)', designation, re.IGNORECASE)
        if not m:
            return None
        major = float(m.group(1))

        if pitch is None:
            pitch = _METRIC_COARSE_PITCH.get(major)
            if pitch is None:
                return None

        return major - pitch

    elif system == 'imperial':
        # Normalize designation for lookup: strip spaces, uppercase
        norm = designation.replace(' ', '').upper()

        # Try direct lookup
        for key, drill in _IMPERIAL_TAP_DRILLS.items():
            if key.replace(' ', '').upper() == norm:
                return drill * 25.4  # convert to mm

        # Try partial match (designation without class suffix)
        import re
        m = re.match(r'([\d/#]+\s*-\s*\d+)', designation)
        if m:
            base = m.group(1).replace(' ', '').upper()
            for key, drill in _IMPERIAL_TAP_DRILLS.items():
                if key.replace(' ', '').upper().startswith(base):
                    return drill * 25.4

        return None

    return None


def _find_best_match(tap_drill_mm, depth_mm, hole_profiles, already_matched):
    """
    Find the hole profile that best matches the expected tap drill diameter.

    Returns (hole_index, confidence_str) or None.
    """
    # Tolerance: ±0.3mm for diameter match (tap drill charts have some spread)
    DIA_TOL_MM = 0.3
    # Depth tolerance: ±2mm (drawing depth is nominal, STEP is exact)
    DEPTH_TOL_MM = 2.0

    candidates = []

    for i, hp in enumerate(hole_profiles):
        if i in already_matched:
            continue

        hole_dia_mm = hp['rep_radius_mm'] * 2.0
        dia_error = abs(hole_dia_mm - tap_drill_mm)

        if dia_error > DIA_TOL_MM:
            continue

        # Diameter matches — check depth if available
        depth_match = True
        if depth_mm is not None:
            hole_depth = hp.get('total_height_mm', 0)
            if abs(hole_depth - depth_mm) > DEPTH_TOL_MM:
                depth_match = False

        # Score: lower error = better match
        score = dia_error
        if depth_match and depth_mm is not None:
            score *= 0.5  # bonus for depth match

        candidates.append((i, score, depth_match))

    if not candidates:
        return None

    # Pick best by score
    candidates.sort(key=lambda x: x[1])
    best_idx, best_score, best_depth = candidates[0]

    # Confidence
    if best_score < 0.05 and best_depth:
        confidence = 'high'
    elif best_score < 0.15:
        confidence = 'medium'
    else:
        confidence = 'low'

    return best_idx, confidence