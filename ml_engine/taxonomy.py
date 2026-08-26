"""The land cover taxonomy: classes, display colours, and endmember spectra.

Single source of truth. `backend/config.py` and `frontend/src/lib/constants.js` mirror
this list and must be changed with it -- they are separate deployment units and cannot
import from here.

Seven classes rather than the five in the original MVP spec. Roads were split out of
built-up because a road network is a distinct intelligence product from a building
footprint: the sponsoring use case is detecting *changes to road networks*, which is
meaningless if roads are pooled with the structures beside them. Sand was split from
bare soil because beach, dune and riverbank are the coastal features the problem
statement names, and they are spectrally distinct from tilled earth.

A caveat that belongs in the pitch, not buried here: asphalt, dark roofs and parking
aprons are genuinely similar in six broad bands. Spectral unmixing alone separates road
from built-up only moderately well. What actually recovers a road is its *shape* -- the
spatial allocation stage, which arranges sub-pixels to maximise autocorrelation and so
reconstructs linear continuity that the spectra alone do not carry.
"""

CLASSES = [
    "built_up",
    "road",
    "water",
    "vegetation",
    "cropland",
    "bare_soil",
    "sand",
]

LABELS = {
    "built_up": "Built-up",
    "road": "Road / transport",
    "water": "Water",
    "vegetation": "Vegetation",
    "cropland": "Cropland",
    "bare_soil": "Bare soil",
    "sand": "Sand / beach",
}

# Display palette. Mirrored in backend/services/previews.py and the frontend legend.
COLORS = {
    "built_up":   (214, 96, 77),    # brick red
    "road":       (78, 78, 84),     # dark grey -- reads as tarmac
    "water":      (33, 102, 172),   # blue
    "vegetation": (27, 120, 55),    # dark green
    "cropland":   (166, 219, 108),  # light green
    "bare_soil":  (140, 109, 70),   # brown
    "sand":       (232, 216, 160),  # pale sand
}

# Sentinel-2 L2A surface reflectance endmembers, band order
# B02 (490 nm), B03 (560), B04 (665), B08 (842), B11 (1610), B12 (2190).
#
# EXACTLY ONE ENDMEMBER PER CLASS, and that is a hard constraint, not a simplification.
# Unmixing solves six band equations plus the sum-to-one constraint, so at most seven
# endmembers are resolvable. Go beyond that and the system is underdetermined: infinitely
# many abundance vectors reproduce the observed spectrum exactly, and the solver returns
# whichever one its initialisation happens to reach. Measured with fourteen endmembers,
# a pure asphalt probe came back 45% water and only 29% road. Each spectrum below is
# therefore the representative mid-range material for its class rather than one extreme.
ENDMEMBERS = [
    # name                    B02    B03    B04    B08    B11    B12     class
    ("concrete / roofing",  [0.140, 0.155, 0.175, 0.200, 0.250, 0.230], "built_up"),
    ("weathered asphalt",   [0.090, 0.098, 0.108, 0.118, 0.130, 0.112], "road"),
    ("surface water",       [0.042, 0.056, 0.040, 0.016, 0.008, 0.005], "water"),
    ("dense canopy",        [0.028, 0.055, 0.032, 0.400, 0.180, 0.075], "vegetation"),
    ("cropland",            [0.052, 0.088, 0.082, 0.285, 0.245, 0.145], "cropland"),
    ("bare soil",           [0.105, 0.130, 0.185, 0.245, 0.320, 0.290], "bare_soil"),
    ("beach sand",          [0.185, 0.240, 0.300, 0.360, 0.420, 0.375], "sand"),
]

ENDMEMBER_NAMES = [row[0] for row in ENDMEMBERS]
ENDMEMBER_SPECTRA = [row[1] for row in ENDMEMBERS]
ENDMEMBER_CLASS = [CLASSES.index(row[2]) for row in ENDMEMBERS]

# Classes whose real-world form is elongated. The sub-pixel allocator scores these with
# oriented kernels and takes the best-aligned direction, rather than counting neighbours
# in all directions equally. An isotropic score rewards compact blobs, which is right for
# a field or a lake and wrong for a road: a road sub-pixel should be rewarded for having
# neighbours *in line with it*, which is what reconstructs continuity across a corridor
# only one or two sub-pixels wide.
LINEAR_CLASSES = ["road"]
LINEAR_CLASS_IDS = [CLASSES.index(c) for c in LINEAR_CLASSES]

NUM_CLASSES = len(CLASSES)
NODATA = 255
