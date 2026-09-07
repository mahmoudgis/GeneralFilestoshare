# -*- coding: utf-8 -*-
"""
Sheet 3 (southern sheet): 41 59.7'-42 23.3'E, 17 46.5'-18 11.9'N
(Jabal Lababah / Wadi Jawwah / Jabal al Hamra / Ad Darb area).

Same method as sheets 1 and 2: affine georeference fitted to the printed
graticule, on-screen tracing of the red Rijal Almaa boundary and of the heavy
black lineaments, then clipping of the lineaments to the red polygon.

Two things are specific to this sheet:
  * the printed graticule is NOT square here - 75.90 px per longitude minute
    against 72.52 px per latitude minute - so x and y are fitted independently;
  * the coloured geology only covers the part of the sheet SOUTH of 18 00'.
    North of that line the sheet is blank, so no fault can be digitised there
    even where it lies inside the red polygon.

Outputs (EPSG:4326):
    faults_sheet3.shp        - fault / lineament traces clipped to the polygon
    study_area_sheet3.shp    - the red boundary as a POLYGON (+ areas in km2)
    faults_sheet3.geojson    - faults as GeoJSON
    preview_sheet3.svg       - QC overlay in the original image pixel frame
"""
import json, math, os
import shapefile  # pyshp

OUT = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- georeference
X0_PX, X0_MIN = 85.0, 0.0        # 42 deg 00' meridian
PX_PER_MIN_X = 75.90             # 42 21' at x = 1683 px
Y0_PX, Y0_MIN = 925.0, 0.0       # 18 deg 00' parallel
PX_PER_MIN_Y = 72.52             # 17 48' at y = 1795 px

IMG_W, IMG_H = 1907, 1919
FRAME = dict(left=62.0, right=1852.0, top=62.0, bottom=1902.0)   # map neatline
GEOL_TOP_PX = 930.0              # coloured geology starts here (18 00')


def lon(x):
    return 42.0 + (X0_MIN + (x - X0_PX) / PX_PER_MIN_X) / 60.0


def lat(y):
    return 18.0 + (Y0_MIN - (y - Y0_PX) / PX_PER_MIN_Y) / 60.0


def to_geo(pts):
    return [(round(lon(x), 6), round(lat(y), 6)) for x, y in pts]


# ------------------------------------------- red boundary of Rijal Almaa (poly)
# Clockwise in pixel space. The ring is closed along the neatline where the red
# line leaves the sheet. The Jabal Baqarah / gmn embayment in the centre-north
# (42 04.3'-42 14.2'E, south of 18 03.4') is OUTSIDE the governorate, exactly as
# on sheet 2, so the ring runs around it.
RED_RING = [
    (62, 505), (100, 500), (140, 495), (170, 488), (200, 482),        # NW limb
    (230, 478), (270, 485), (300, 490),
    (310, 470), (322, 440), (330, 420), (340, 412), (355, 405),       # W limb up
    (368, 378), (378, 340), (390, 300), (395, 255), (405, 215),
    (410, 175), (400, 140), (392, 100), (390, 62),
    (1638, 62),                                                       # N neatline
    (1640, 90), (1644, 120), (1648, 150), (1652, 180), (1655, 210),   # E limb
    (1658, 240), (1662, 270), (1670, 300), (1680, 320), (1690, 340),
    (1700, 360), (1708, 390), (1712, 420), (1715, 450), (1718, 480),
    (1720, 510), (1722, 540), (1725, 570), (1728, 600), (1730, 630),
    (1728, 660), (1725, 690), (1722, 720), (1720, 750), (1715, 780),
    (1710, 810), (1705, 840), (1700, 870), (1695, 900), (1690, 925),
    (1680, 940), (1670, 960), (1660, 980), (1645, 1000), (1630, 1020),
    (1620, 1040), (1610, 1060), (1600, 1080), (1590, 1100), (1580, 1120),
    (1570, 1140), (1560, 1160), (1550, 1180), (1540, 1200), (1530, 1230),
    (1525, 1260), (1520, 1290), (1515, 1320), (1510, 1350), (1505, 1380),
    (1500, 1410), (1495, 1440), (1488, 1470), (1478, 1500), (1470, 1520),
    (1462, 1495), (1450, 1478), (1430, 1466), (1400, 1456), (1370, 1446),
    (1340, 1436), (1310, 1426), (1285, 1414), (1265, 1400), (1252, 1380),
    (1242, 1352), (1236, 1322), (1231, 1292), (1226, 1262), (1223, 1232),
    (1220, 1202), (1216, 1172), (1211, 1142), (1206, 1112), (1201, 1082),
    (1196, 1052), (1191, 1022), (1186, 992), (1176, 962), (1160, 925),
    (1150, 890), (1135, 850), (1120, 800), (1110, 760), (1100, 720),  # notch E
    (1090, 690), (1080, 672),
    (1060, 676), (1030, 680), (990, 684), (950, 688), (910, 690),     # notch N
    (870, 695), (830, 700), (800, 706), (788, 710), (770, 712),
    (752, 708), (730, 703), (700, 698), (668, 691), (636, 686),
    (604, 683), (572, 680), (540, 678), (508, 680), (482, 686),
    (468, 694), (456, 710), (444, 726), (434, 744), (427, 764),       # notch W
    (424, 786), (430, 800), (422, 820), (410, 834), (406, 850),
    (412, 864), (416, 882), (419, 900),
    (426, 955), (433, 1005), (440, 1055), (443, 1085), (438, 1115),   # W limb dn
    (432, 1150), (426, 1185), (420, 1215), (414, 1250), (407, 1290),
    (400, 1330), (392, 1370), (384, 1410), (376, 1450), (368, 1490),
    (358, 1530), (348, 1570), (338, 1610), (328, 1645), (322, 1660),
    (300, 1672), (260, 1688), (220, 1704), (180, 1720), (140, 1738),  # SW limb
    (100, 1755), (62, 1768),
]


def in_ring(p, ring):
    x, y = p
    c = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            if x < x1 + (y - y1) * (x2 - x1) / float(y2 - y1):
                c = not c
    return c


def inside(p):
    """Inside the red polygon AND on the part of the sheet that carries geology."""
    x, y = p
    return (FRAME['left'] <= x <= FRAME['right']
            and GEOL_TOP_PX <= y <= FRAME['bottom']
            and in_ring(p, RED_RING))


def clip(line):
    def cross(a, b):
        lo, hi = (a, b) if inside(a) else (b, a)
        for _ in range(45):
            mid = ((lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0)
            if inside(mid):
                lo = mid
            else:
                hi = mid
        return lo

    parts, cur = [], []
    for a, b in zip(line, line[1:]):
        ia, ib = inside(a), inside(b)
        if ia and ib:
            if not cur:
                cur = [a]
            cur.append(b)
        elif ia and not ib:
            if not cur:
                cur = [a]
            cur.append(cross(a, b))
            parts.append(cur)
            cur = []
        elif ib and not ia:
            cur = [cross(a, b), b]
    if cur:
        parts.append(cur)
    return [p for p in parts if len(p) >= 2]


# ------------------------------------------------------- digitised lineaments
# Only two parts of the polygon carry mapped geology on this sheet: the western
# strip (west of the Jabal Baqarah embayment) and the southward-pointing salient
# between 42 14' and 42 21'E. Everything digitised below lies in one of them.
FAULTS = [
    # --- western strip -------------------------------------------------------
    ("W01", "low", "Lineament SE of Jabal Lababah, western strip",
     [(300, 960), (322, 1015), (344, 1070), (364, 1125), (380, 1175)]),
    ("W02", "low", "Lineament in the gmm granite, central western strip",
     [(200, 1250), (224, 1315), (248, 1382), (268, 1445), (284, 1495)]),
    ("W03", "low", "Lineament in the Qrs cover near Wadi Jawwah, SW of the strip",
     [(120, 1520), (146, 1590), (172, 1660), (196, 1725), (215, 1780)]),
    # --- southern salient (42 14'-42 21'E) ----------------------------------
    ("S01", "medium", "NNW-SSE lineament on the western edge of the salient",
     [(1185, 935), (1215, 1030), (1244, 1125), (1272, 1220), (1300, 1315),
      (1326, 1400)]),
    ("S02", "high", "NNW-SSE fault bounding the as unit west of the hatched band",
     [(1250, 935), (1282, 1030), (1313, 1125), (1343, 1220), (1372, 1315),
      (1398, 1400)]),
    ("S03", "high", "Western margin of the cross-hatched band, Jabal al Hamra",
     [(1320, 935), (1352, 1030), (1383, 1125), (1413, 1220), (1441, 1315),
      (1466, 1400)]),
    ("S04", "medium", "Eastern margin of the cross-hatched band",
     [(1395, 935), (1427, 1030), (1457, 1122), (1486, 1214), (1512, 1300)]),
    ("S05", "medium", "NNW-SSE fault in the as unit, central salient",
     [(1470, 935), (1501, 1027), (1530, 1118), (1557, 1206), (1580, 1285)]),
    ("S06", "medium", "NNW-SSE fault east of S05, narrowing part of the salient",
     [(1545, 940), (1575, 1028), (1603, 1114), (1628, 1195)]),
    ("S07", "low", "Short lineament close to the eastern red boundary",
     [(1620, 940), (1648, 1022), (1673, 1100)]),
]

PRJ = ('GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",'
       'SPHEROID["WGS_1984",6378137.0,298.257223563]],'
       'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]')


def write_prj(base):
    open(base + ".prj", "w").write(PRJ)
    open(base + ".cpg", "w").write("UTF-8")


def geod_len_m(pts):
    R = 6371008.8
    t = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        m = math.radians((y1 + y2) / 2.0)
        t += R * math.hypot(math.radians(x2 - x1) * math.cos(m),
                            math.radians(y2 - y1))
    return t


def strike_deg(pts):
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    m = math.radians((y1 + y2) / 2.0)
    return (math.degrees(math.atan2(math.radians(x2 - x1) * math.cos(m),
                                    math.radians(y2 - y1))) + 360.0) % 180.0


def trend_name(s):
    for lo, hi, nm in ((0, 11.25, "N-S"), (11.25, 33.75, "NNE-SSW"),
                       (33.75, 56.25, "NE-SW"), (56.25, 78.75, "ENE-WSW"),
                       (78.75, 101.25, "E-W"), (101.25, 123.75, "WNW-ESE"),
                       (123.75, 146.25, "NW-SE"), (146.25, 168.75, "NNW-SSE"),
                       (168.75, 180.01, "N-S")):
        if lo <= s < hi:
            return nm
    return "N-S"


def area_km2(ring_geo):
    R = 6371008.8
    lat0 = sum(p[1] for p in ring_geo) / len(ring_geo)
    lon0 = sum(p[0] for p in ring_geo) / len(ring_geo)
    pts = [(R * math.radians(a - lon0) * math.cos(math.radians(b)),
            R * math.radians(b - lat0)) for a, b in ring_geo]
    s = sum(x1 * y2 - x2 * y1
            for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]))
    return abs(s) / 2.0 / 1e6


# --------------------------------------------------------------- study area shp
ring_geo = to_geo([(float(a), float(b)) for a, b in RED_RING])
AREA = area_km2(ring_geo)
PERIM = geod_len_m(ring_geo + [ring_geo[0]]) / 1000.0

# how much of that polygon actually carries mapped geology (south of 18 00')
step = 2.0
tot_c = geo_c = 0
y = FRAME['top']
while y < FRAME['bottom']:
    x = FRAME['left']
    while x < FRAME['right']:
        if in_ring((x, y), RED_RING):
            tot_c += 1
            if y >= GEOL_TOP_PX:
                geo_c += 1
        x += step
    y += step
GEOL_AREA = AREA * geo_c / float(tot_c) if tot_c else 0.0

sbase = os.path.join(OUT, "study_area_sheet3")
sw = shapefile.Writer(sbase, shapeType=shapefile.POLYGON)
sw.field("FID", "N", 6, 0)
sw.field("NAME", "C", 70)
sw.field("AREA_KM2", "N", 14, 3)
sw.field("GEOL_KM2", "N", 14, 3)
sw.field("PERIM_KM", "N", 14, 3)
sw.field("NOTE", "C", 150)
ring = [list(p) for p in ring_geo]
if sum(ring[i][0] * ring[(i + 1) % len(ring)][1]
       - ring[(i + 1) % len(ring)][0] * ring[i][1] for i in range(len(ring))) > 0:
    ring.reverse()
sw.poly([ring + [ring[0]]])
sw.record(1, "Rijal Almaa Governorate - on-sheet part (sheet 42E south)",
          round(AREA, 3), round(GEOL_AREA, 3), round(PERIM, 3),
          "AREA_KM2 is the whole on-sheet polygon; GEOL_KM2 is only the part "
          "south of 18 00' that carries coloured geology and can be interpreted")
sw.close()
write_prj(sbase)

# ------------------------------------------------------------------ faults shp
base = os.path.join(OUT, "faults_sheet3")
w = shapefile.Writer(base, shapeType=shapefile.POLYLINE)
for f, t, sz, d in (("FID", "N", 6, 0), ("NAME", "C", 20, 0),
                    ("FEATURE", "C", 30, 0), ("TREND", "C", 12, 0),
                    ("STRIKE_DEG", "N", 8, 1), ("LENGTH_M", "N", 12, 1),
                    ("CONF", "C", 10, 0), ("METHOD", "C", 45, 0),
                    ("SOURCE", "C", 60, 0), ("NOTE", "C", 120, 0)):
    w.field(f, t, sz, d) if t == "N" else w.field(f, t, sz)

feats, preview_px, fid = [], [], 0
for name, conf, note, px in FAULTS:
    for k, part in enumerate(clip([(float(a), float(b)) for a, b in px])):
        fid += 1
        g = to_geo(part)
        s = strike_deg(g)
        nm = name if k == 0 else "%s_%d" % (name, k + 1)
        w.line([[list(p) for p in g]])
        w.record(fid, nm, "Fault / lineament", trend_name(s), round(s, 1),
                 round(geod_len_m(g), 1), conf,
                 "Visual interpretation (on-screen digitising)",
                 "Scanned USGS geologic map sheet, Dar Al Asfahani print", note)
        preview_px.append(part)
        feats.append({"type": "Feature",
                      "properties": {"FID": fid, "NAME": nm,
                                     "FEATURE": "Fault / lineament",
                                     "TREND": trend_name(s), "STRIKE_DEG": round(s, 1),
                                     "LENGTH_M": round(geod_len_m(g), 1),
                                     "CONF": conf, "NOTE": note},
                      "geometry": {"type": "LineString",
                                   "coordinates": [list(p) for p in g]}})
w.close()
write_prj(base)
json.dump({"type": "FeatureCollection",
           "crs": {"type": "name",
                   "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
           "features": feats}, open(base + ".geojson", "w"), indent=1)

# --------------------------------------------------------------- preview (SVG)
o = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
     'viewBox="0 0 %d %d">' % (IMG_W, IMG_H, IMG_W, IMG_H),
     '<rect width="100%%" height="100%%" fill="#fdfaf5"/>',
     '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#efe7d8"/>'
     % (FRAME['left'], FRAME['top'], FRAME['right'] - FRAME['left'],
        GEOL_TOP_PX - FRAME['top']),
     '<text x="%.1f" y="%.1f" font-size="30" fill="#7a6a52">no geology mapped '
     'on this sheet north of 18%s00\'</text>' % (FRAME['left'] + 400, 520, chr(176))]
for m in range(0, 24, 3):
    x = X0_PX + m * PX_PER_MIN_X
    if x > FRAME['right']:
        continue
    o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#e8863c" '
             'stroke-width="1.2"/>' % (x, FRAME['top'], x, FRAME['bottom']))
    o.append('<text x="%.1f" y="%.1f" font-size="26" text-anchor="middle" '
             'fill="#8a5a2b">42%s%s</text>'
             % (x, FRAME['bottom'] + 34, chr(176), "" if m == 0 else "%d'" % m))
for m in range(-12, 13, 3):
    y = Y0_PX - m * PX_PER_MIN_Y
    if not (FRAME['top'] <= y <= FRAME['bottom']):
        continue
    o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#e8863c" '
             'stroke-width="1.2"/>' % (FRAME['left'], y, FRAME['right'], y))
    d, mm = (18, m) if m >= 0 else (17, 60 + m)
    o.append('<text x="%.1f" y="%.1f" font-size="26" fill="#8a5a2b">%d%s%s</text>'
             % (FRAME['right'] + 10, y + 9, d, chr(176),
                "" if (d == 18 and mm == 0) else "%d'" % mm))
o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="none" '
         'stroke="#222" stroke-width="3"/>'
         % (FRAME['left'], FRAME['top'], FRAME['right'] - FRAME['left'],
            FRAME['bottom'] - FRAME['top']))
o.append('<polygon fill="#e01b1b" fill-opacity="0.08" stroke="#e01b1b" '
         'stroke-width="10" stroke-linejoin="round" points="%s"/>'
         % " ".join("%.1f,%.1f" % p for p in RED_RING))
for part in preview_px:
    o.append('<polyline fill="none" stroke="#12261a" stroke-width="5" '
             'stroke-linecap="round" points="%s"/>'
             % " ".join("%.1f,%.1f" % p for p in part))
o.append('<text x="70" y="%d" font-size="28" fill="#222">Sheet 42E south - '
         'faults clipped to the red polygon (%.0f km2 on sheet, %.0f km2 with '
         'geology) - QC overlay</text>' % (FRAME['bottom'] + 78, AREA, GEOL_AREA))
o.append('</svg>')
open(os.path.join(OUT, "preview_sheet3.svg"), "w").write("\n".join(o))

print("on-sheet polygon: %.2f km2 (with geology: %.2f km2), perimeter %.2f km"
      % (AREA, GEOL_AREA, PERIM))
print("fault features: %d" % fid)
tot = 0.0
for r in shapefile.Reader(base).records():
    tot += r[5]
    print("  %-8s %-9s strike %5.1f  len %8.0f m  %s" % (r[1], r[3], r[4], r[5], r[6]))
print("total fault length: %.2f km" % (tot / 1000.0))
if fid:
    print("bbox:", [round(v, 5) for v in shapefile.Reader(base).bbox])
