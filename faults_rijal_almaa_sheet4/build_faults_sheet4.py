# -*- coding: utf-8 -*-
"""
Sheet 4 (coastal sheet): 41 46'-42 03.8'E, 17 42.5'-18 01.3'N
(Jabal Hashahish / Khawr al Makra / Ash Shuqayq coastal plain).

Same method as sheets 1-3. Two things dominate the result here:

  * almost the whole polygon is Quaternary cover - Qb basalt, Qs / Qal / Qes
    sand and alluvium, Qsb sabkha - which carries no mapped faults at all.
    The only basement inside the red line is the NE corner (gt / bhu / gr,
    roughly 41 56'-42 01'E and 17 55'-18 00'N), and that is where every trace
    below comes from;
  * the long parallel double lines crossing the coastal plain are the coast
    road and tracks, NOT faults. They are deliberately not digitised.

Outputs (EPSG:4326):
    faults_sheet4.shp / .geojson, study_area_sheet4.shp, preview_sheet4.svg
"""
import json, math, os
import shapefile

OUT = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- georeference
X0_PX, X0_MIN = 52.0, 46.0       # 41 deg 46' meridian
PX_PER_MIN_X = 75.625            # 42 02' at x = 1262 px
Y0_PX, Y0_MIN = 145.0, 0.0       # 18 deg 00' parallel
PX_PER_MIN_Y = 75.50             # 17 44' at y = 1353 px

IMG_W, IMG_H = 1456, 1541
FRAME = dict(left=52.0, right=1400.0, top=45.0, bottom=1470.0)
GEOL_RIGHT_PX = 1195.0           # coloured geology stops here (approx 42 01.1')
GEOL_NE_X = 1110.0               # NE corner above 18 00' is blank beyond this


def lon(x):
    return 41.0 + (X0_MIN + (x - X0_PX) / PX_PER_MIN_X) / 60.0


def lat(y):
    return 18.0 + (Y0_MIN - (y - Y0_PX) / PX_PER_MIN_Y) / 60.0


def to_geo(pts):
    return [(round(lon(x), 6), round(lat(y), 6)) for x, y in pts]


def has_geology(p):
    x, y = p
    return x <= GEOL_RIGHT_PX and (y >= Y0_PX or x <= GEOL_NE_X)


# ------------------------------------------- red boundary of Rijal Almaa (poly)
RED_RING = [
    (620, 45), (560, 52), (500, 60), (430, 72), (370, 85),            # NW limb
    (320, 95), (288, 108),
    (280, 150), (272, 200), (262, 250), (252, 300), (242, 350),       # W limb
    (232, 400), (222, 450), (212, 500), (200, 550), (188, 600),
    (176, 650), (164, 700), (152, 750), (140, 790), (128, 820),
    (118, 845), (108, 865), (100, 880), (95, 900),
    (100, 915), (110, 925), (122, 930), (136, 928), (150, 925),       # coast
    (165, 928), (180, 935), (195, 940), (210, 942), (225, 940),
    (232, 948), (238, 958), (245, 970), (251, 985), (258, 995),
    (270, 1000), (285, 1005), (300, 1010), (315, 1015), (330, 1021),
    (345, 1030), (358, 1040), (370, 1050), (382, 1060), (395, 1070),
    (408, 1078), (420, 1085), (432, 1090), (445, 1096), (455, 1106),
    (462, 1120), (468, 1135), (475, 1148), (482, 1156), (490, 1150),
    (500, 1140), (512, 1132), (525, 1128), (540, 1125), (555, 1128),
    (568, 1135), (578, 1145), (588, 1156), (598, 1168), (608, 1180),
    (618, 1192), (628, 1205), (638, 1215), (650, 1225), (662, 1235),
    (675, 1245), (688, 1255), (700, 1265), (712, 1275), (725, 1285),
    (738, 1295), (750, 1305), (762, 1315), (775, 1325), (788, 1335),
    (800, 1345), (812, 1355), (825, 1365), (838, 1375), (850, 1385),
    (862, 1395), (875, 1405), (888, 1415), (900, 1421), (915, 1426),
    (930, 1429), (945, 1431), (960, 1433), (975, 1434),
    (985, 1420), (1000, 1380), (1015, 1340), (1030, 1300),            # SE limb
    (1045, 1260), (1060, 1220), (1072, 1180), (1085, 1140),
    (1095, 1100), (1105, 1060), (1108, 1040),
    (1130, 1020), (1160, 1002), (1190, 984), (1220, 966), (1250, 950),  # E limb
    (1280, 936), (1310, 922), (1340, 910), (1370, 900), (1400, 890),
    (1400, 45),
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
    x, y = p
    return (FRAME['left'] <= x <= FRAME['right']
            and FRAME['top'] <= y <= FRAME['bottom']
            and has_geology(p) and in_ring(p, RED_RING))


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
# All of these lie in the NE basement corner; the rest of the polygon is
# Quaternary cover with no mapped faults.
FAULTS = [
    ("N01", "medium", "ENE-WSW lineament in the bhu unit, NE basement corner",
     [(905, 215), (940, 227), (975, 240), (1010, 252), (1050, 265)]),
    ("N02", "medium", "ENE-WSW lineament north of N01, bhu / gt contact zone",
     [(930, 168), (968, 181), (1005, 196), (1048, 212), (1090, 228)]),
    ("N03", "low", "ENE-WSW lineament in the gt unit south of Jabal Hashahish",
     [(1000, 300), (1038, 313), (1075, 328), (1112, 341), (1150, 352)]),
    ("N04", "low", "Short ENE-WSW lineament, eastern edge of the sheet geology",
     [(1060, 380), (1090, 392), (1120, 404), (1148, 414)]),
    ("N05", "medium", "Dark elongate dyke-like body west of the gr granite",
     [(1035, 470), (1052, 484), (1068, 498), (1084, 511), (1098, 522)]),
    ("N06", "low", "Short lineament in the bhu unit, west of the gr granite",
     [(940, 400), (962, 412), (985, 425), (1007, 437), (1028, 448)]),
]

PRJ = ('GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,'
       '298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]')


def write_prj(b):
    open(b + ".prj", "w").write(PRJ)
    open(b + ".cpg", "w").write("UTF-8")


def geod_len_m(pts):
    R = 6371008.8
    return sum(R * math.hypot(
        math.radians(x2 - x1) * math.cos(math.radians((y1 + y2) / 2.0)),
        math.radians(y2 - y1)) for (x1, y1), (x2, y2) in zip(pts, pts[1:]))


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


def area_km2(r):
    R = 6371008.8
    la = sum(p[1] for p in r) / len(r)
    lo = sum(p[0] for p in r) / len(r)
    p = [(R * math.radians(a - lo) * math.cos(math.radians(b)),
          R * math.radians(b - la)) for a, b in r]
    return abs(sum(x1 * y2 - x2 * y1
                   for (x1, y1), (x2, y2) in zip(p, p[1:] + p[:1]))) / 2e6


# --------------------------------------------------------------- study area shp
ring_geo = to_geo([(float(a), float(b)) for a, b in RED_RING])
AREA = area_km2(ring_geo)
PERIM = geod_len_m(ring_geo + [ring_geo[0]]) / 1000.0

step, tot_c, geo_c = 2.0, 0, 0
y = FRAME['top']
while y < FRAME['bottom']:
    x = FRAME['left']
    while x < FRAME['right']:
        if in_ring((x, y), RED_RING):
            tot_c += 1
            if has_geology((x, y)):
                geo_c += 1
        x += step
    y += step
GEOL_AREA = AREA * geo_c / float(tot_c)

sbase = os.path.join(OUT, "study_area_sheet4")
sw = shapefile.Writer(sbase, shapeType=shapefile.POLYGON)
for f, t, sz, d in (("FID", "N", 6, 0), ("NAME", "C", 70, 0),
                    ("AREA_KM2", "N", 14, 3), ("GEOL_KM2", "N", 14, 3),
                    ("PERIM_KM", "N", 14, 3), ("NOTE", "C", 150, 0)):
    sw.field(f, t, sz, d) if t == "N" else sw.field(f, t, sz)
ring = [list(p) for p in ring_geo]
if sum(ring[i][0] * ring[(i + 1) % len(ring)][1]
       - ring[(i + 1) % len(ring)][0] * ring[i][1] for i in range(len(ring))) > 0:
    ring.reverse()
sw.poly([ring + [ring[0]]])
sw.record(1, "Rijal Almaa Governorate - on-sheet part (sheet 41E coastal)",
          round(AREA, 3), round(GEOL_AREA, 3), round(PERIM, 3),
          "Almost entirely Quaternary cover; the only basement inside the "
          "polygon is the NE corner, so the fault count here is genuinely low")
sw.close()
write_prj(sbase)

# ------------------------------------------------------------------ faults shp
base = os.path.join(OUT, "faults_sheet4")
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
     % (GEOL_RIGHT_PX, FRAME['top'], FRAME['right'] - GEOL_RIGHT_PX,
        FRAME['bottom'] - FRAME['top']),
     '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#efe7d8"/>'
     % (GEOL_NE_X, FRAME['top'], GEOL_RIGHT_PX - GEOL_NE_X, Y0_PX - FRAME['top'])]
for m in range(46, 65, 2):
    x = X0_PX + (m - X0_MIN) * PX_PER_MIN_X
    if not (FRAME['left'] <= x <= FRAME['right']):
        continue
    o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#e8863c" '
             'stroke-width="1.2"/>' % (x, FRAME['top'], x, FRAME['bottom']))
    d, mm = (41, m) if m < 60 else (42, m - 60)
    o.append('<text x="%.1f" y="%.1f" font-size="22" text-anchor="middle" '
             'fill="#8a5a2b">%d%s%s</text>'
             % (x, FRAME['bottom'] + 30, d, chr(176), "" if mm == 0 else "%d'" % mm))
for m in range(-18, 3, 2):
    y = Y0_PX - m * PX_PER_MIN_Y
    if not (FRAME['top'] <= y <= FRAME['bottom']):
        continue
    o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#e8863c" '
             'stroke-width="1.2"/>' % (FRAME['left'], y, FRAME['right'], y))
    d, mm = (18, m) if m >= 0 else (17, 60 + m)
    o.append('<text x="%.1f" y="%.1f" font-size="22" fill="#8a5a2b">%d%s%s</text>'
             % (FRAME['right'] + 8, y + 8, d, chr(176),
                "" if mm == 0 else "%d'" % mm))
o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="none" '
         'stroke="#222" stroke-width="2.5"/>'
         % (FRAME['left'], FRAME['top'], FRAME['right'] - FRAME['left'],
            FRAME['bottom'] - FRAME['top']))
o.append('<polygon fill="#e01b1b" fill-opacity="0.08" stroke="#e01b1b" '
         'stroke-width="9" stroke-linejoin="round" points="%s"/>'
         % " ".join("%.1f,%.1f" % p for p in RED_RING))
for part in preview_px:
    o.append('<polyline fill="none" stroke="#12261a" stroke-width="5" '
             'stroke-linecap="round" points="%s"/>'
             % " ".join("%.1f,%.1f" % p for p in part))
o.append('<text x="60" y="%d" font-size="24" fill="#222">Sheet 41E coastal - '
         '%d traces, all in the NE basement corner; the rest of the polygon is '
         'Quaternary cover</text>' % (FRAME['bottom'] + 66, fid))
o.append('</svg>')
open(os.path.join(OUT, "preview_sheet4.svg"), "w").write("\n".join(o))

print("on-sheet polygon: %.2f km2 (with geology: %.2f km2), perimeter %.2f km"
      % (AREA, GEOL_AREA, PERIM))
print("fault features: %d" % fid)
tot = 0.0
for r in shapefile.Reader(base).records():
    tot += r[5]
    print("  %-8s %-9s strike %5.1f  len %8.0f m  %s" % (r[1], r[3], r[4], r[5], r[6]))
print("total fault length: %.2f km" % (tot / 1000.0))
print("bbox:", [round(v, 5) for v in shapefile.Reader(base).bbox])
