# sourcing/config.py
# Central location for all tunable constants.
# Import from here everywhere — never hardcode thresholds in feature modules.

# ---------------------------------------------------------------------------
# CHAMFER CONSTANTS
# ---------------------------------------------------------------------------
# Semi-angles (degrees) considered standard chamfer angles.
CHAMFER_SEMI_ANGLES_DEG     = {45.0, 30.0, 60.0}
CHAMFER_ANGLE_TOL_DEG       = 2.0

# A pointed cone (minor_radius ≈ 0) is always a drill tip — never a chamfer.
CHAMFER_MIN_MINOR_RADIUS_MM = 0.1


# ---------------------------------------------------------------------------
# THIN WALL CONSTANTS
# ---------------------------------------------------------------------------
# Aspect ratio thresholds (height : thickness).
THIN_WALL_WARNING_RATIO  = 8.0    # flag as warning above this ratio
THIN_WALL_CRITICAL_RATIO = 10.0   # flag as critical above this ratio

# Maximum thickness to bother checking — walls thicker than this are never
# flagged regardless of height.
THIN_WALL_MAX_THICKNESS_MM = 50.0

# UV sampling grid density for ray casting on curved faces (N × N per face).
THIN_WALL_SAMPLE_GRID = 5

# Minimum UV extent (in model units) for a curved face to be ray-cast.
# Faces smaller than this in both directions are skipped (e.g. small fillets).
THIN_WALL_MIN_FACE_EXTENT = 0.002  # 2 mm at scale 1.0

# Cluster radius: thin sample points within this distance (mm) of each other
# are merged into the same thin wall region. Set relative to typical part size —
# a fixed small value causes the same wall to be reported many times on large parts.
THIN_WALL_CLUSTER_DIST_MM = 20.0

# Antiparallel normal tolerance for planar pairing (dot product threshold).
THIN_WALL_ANTIPARALLEL_TOL = 0.99

# Minimum fraction of centroid-to-centroid vector that must be along the
# wall normal for two planar faces to be considered genuinely opposing.
THIN_WALL_OPPOSING_TOL = 0.95

# Concentric cylinder detection tolerances
COAXIAL_DIST_TOL_MM = 0.5    # axis lines must be within this distance to be coaxial
PARALLEL_DOT_TOL    = 0.999  # axes must satisfy |dot| >= this to be considered parallel


# ---------------------------------------------------------------------------
# CHAMFER FACE CLASSIFICATION CONSTANTS
# ---------------------------------------------------------------------------
# Tolerance around standard chamfer angles (30°, 45°, 60°) from any principal
# axis. A planar face whose normal is within this tolerance of a standard
# chamfer angle is a candidate chamfer, subject to the width ratio check below.
SETUP_CHAMFER_ANGLE_TOL_DEG = 5.0

# Chamfer width / edge length ratio threshold. A planar face at a chamfer
# angle is classified as a chamfer only if its shorter dimension divided by
# its longer dimension is below this value. Prevents large bevelled surfaces
# from being misclassified as chamfers.
# 0.25 → chamfer removes less than 25% of the adjacent edge length.
SETUP_CHAMFER_WIDTH_RATIO      = 0.15   # chamfer width / parent edge length must be below this
SETUP_CHAMFER_MAX_ABS_WIDTH_MM = 10.0   # faces narrower than this are always chamfers regardless of ratio
SETUP_CHAMFER_MAX_ASPECT_RATIO = 0.5    # shorter/longer — faces above this are too square to be a chamfer

# Angles at which a stock fixture (sine vise, angle plate) commonly exists.
# An off-axis setup at one of these angles can be done on a 3-axis machine
# with a standard fixture. Any other angle requires 5-axis-indexed.
SETUP_STANDARD_FIXTURE_ANGLES_DEG = (30.0, 45.0, 60.0)
SETUP_STANDARD_FIXTURE_ANGLE_TOL_DEG = 2.0

# ---------------------------------------------------------------------------
# SETUP ANALYSIS CONSTANTS
# ---------------------------------------------------------------------------
# Angular radius for Gauss map clustering. Directions within this angle of
# each other are grouped into the same cluster / candidate setup direction.
# 15° absorbs minor normal variation on drafted faces while keeping genuinely
# distinct setup directions separate. Tune down to 10° for very precise parts,
# up to 20° if STEP exports have noisy normals.
SETUP_CLUSTER_ANGLE_DEG = 15.0

# Cluster centroid within this angle of a principal axis (±X ±Y ±Z) is
# snapped to that axis and classified as 3-axis-standard. Intentionally
# looser than SETUP_CLUSTER_ANGLE_DEG — a slightly off-axis part face
# should not force a special-fixture classification.
SETUP_PRINCIPAL_AXIS_TOL_DEG = 10.0

# Concern thresholds — holes (tightest: drill/bore wants to be on-axis)
SETUP_HOLE_ADVISORY_DEG  =  3.0   # starts affecting tool life and runout
SETUP_HOLE_WARNING_DEG   =  8.0   # needs pecking cycle or special tooling
SETUP_HOLE_CRITICAL_DEG  = 15.0   # effectively requires its own indexed setup

# Concern thresholds — pocket floors
SETUP_POCKET_ADVISORY_DEG  = 10.0  # floor finish starts degrading
SETUP_POCKET_WARNING_DEG   = 20.0  # significant depth-of-cut reduction
SETUP_POCKET_CRITICAL_DEG  = 35.0  # floor essentially inaccessible flat

# Concern thresholds — planar faces (loosest: face milling tolerates more)
SETUP_PLANAR_ADVISORY_DEG  = 20.0
SETUP_PLANAR_WARNING_DEG   = 35.0
SETUP_PLANAR_CRITICAL_DEG  = 50.0

# ---------------------------------------------------------------------------
# EDGE ROUND vs FILLET CLASSIFICATION
# A convex partial cylinder is an 'edge_round' (millable with standard end mill,
# contributes to setup analysis) if BOTH conditions hold:
#   - radius is large enough to be a design-intent edge, not a tooling corner
#   - axial height is short relative to radius (low h/r = shallow arc in context)
# If either condition fails it's treated as a true 'fillet' (special tooling, excluded from setup).
FILLET_EDGE_ROUND_MIN_RADIUS_MM = 5.0   # below this radius → always a true fillet regardless of ratio
FILLET_EDGE_ROUND_MAX_HR_RATIO  = 3.0   # height / radius must be below this to be an edge round

# DFM ANALYSIS CONSTANTS
# ---------------------------------------------------------------------------

# Hole L/D ratio thresholds (length-to-diameter, i.e. depth / (2*radius))
DFM_HOLE_LD_ADVISORY  = 3.0   # deeper than 3× dia → standard tooling reaches limit
DFM_HOLE_LD_WARNING   = 6.0   # extended tooling or pecking required
DFM_HOLE_LD_CRITICAL  = 10.0  # gun-drilling territory, specialist process

# Small hole diameter thresholds (diameter in mm)
DFM_HOLE_SMALL_ADVISORY_DIA_MM  = 1.5   # specialty tooling, slower feed rates
DFM_HOLE_SMALL_WARNING_DIA_MM   = 0.8   # micro-drilling, high breakage risk

# Convex fillet radius thresholds (mm)
# Very small convex radii require form tools or tiny ball-nose — expensive
DFM_CONVEX_FILLET_WARNING_R_MM = 1.0   # sub-1mm convex radius → warning

# Convex fillet axis alignment threshold.
# If |dot(fillet_axis, fixturing_approach)| >= this value, the tool can
# traverse the fillet with a standard end mill (axis is parallel to approach).
# Below this threshold the axis is too perpendicular — ball-nose required.
DFM_CONVEX_FILLET_AXIS_ALIGNED_TOL = 0.9

# Concave fillet radius thresholds (mm)
# Smallest concave radius constrains end mill selection (tool dia ≤ 2×radius)
DFM_CONCAVE_FILLET_SMALL_WARNING_R_MM = 1.5  # ≤ 3mm end mill, slow feeds

# ---------------------------------------------------------------------------
# Tool access — minimum tool diameter per fixturing
# ---------------------------------------------------------------------------

# Planar pass: face normal must satisfy |dot(normal, approach)| < this to be
# considered a "wall" face (as opposed to a floor/ceiling face).
# 0.5 = normals within 60° of perpendicular to approach.
TOOL_ACCESS_WALL_PERP_TOL = 0.5

# Maximum gap to consider as a constraint. Gaps wider than this don't restrict
# typical milling tools and are excluded from results.
TOOL_ACCESS_MAX_GAP_MM = 50.0

# UV sample grid for ray cast pass (N×N points per face).
# Smaller than thin_walls (5) — no refinement pass needed here.
TOOL_ACCESS_SAMPLE_GRID = 4

# Antiparallel tolerance for planar wall pairs (same as thin_walls).
TOOL_ACCESS_ANTIPARALLEL_TOL = 0.99

# Opposing tolerance: centroid-to-centroid vector must align this much with
# face normal for two planar faces to be considered an opposing pair.
TOOL_ACCESS_OPPOSING_TOL = 0.85

# ---------------------------------------------------------------------------
# Deep feature L/D thresholds (fixturing-based)
# ---------------------------------------------------------------------------

# A face normal must satisfy |dot(normal, approach)| >= this to be considered
# a floor face (parallel to approach = perpendicular to tool motion).
DFM_DEEP_FEATURE_FLOOR_TOL = 0.95

# L/D thresholds for depth / min_tool_dia ratio
DFM_DEEP_FEATURE_LD_ADVISORY  = 3.0
DFM_DEEP_FEATURE_LD_WARNING   = 6.0
DFM_DEEP_FEATURE_LD_CRITICAL  = 10.0