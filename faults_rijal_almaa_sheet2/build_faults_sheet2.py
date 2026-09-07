# -*- coding: utf-8 -*-
"""
Sheet 2 (adjacent sheet east of the first one): 42 00'-42 28'E, 17 59.7'-18 28'N
(Jabal Sawda' / Wadi al Marabi / Jabal Baqarah area).

Visual (on-screen) digitising of the fault / lineament traces that fall INSIDE
the red boundary polygon of Rijal Almaa Governorate, using the same method as
sheet 1: an affine model fitted to the printed graticule, on-screen tracing of
the heavy black lineaments, then clipping to the red polygon.

Outputs (EPSG:4326):
    faults_sheet2.shp        - fault / lineament traces clipped to the polygon
    study_area_sheet2.shp    - the red boundary as a POLYGON (+ area in km2)
    faults_sheet2.geojson    - faults as GeoJSON
    preview_sheet2.svg       - QC overlay in the original image pixel frame
"""
import json, math, os
import shapefile  # pyshp

OUT = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- georeference
# graticule ticks read off the supplied image (~1456 x 1541 px)
X0_PX, X0_MIN = 47.0, 0.0        # 42 deg 00' meridian
PX_PER_MIN_X = 49.04             # 42 25' at x = 1273 px
Y0_PX, Y0_MIN = 195.0, 25.0      # 18 deg 25' parallel
PX_PER_MIN_Y = 49.20             # 18 00' at y = 1425 px

IMG_W, IMG_H = 1456, 1541
FRAME = dict(left=47.0, right=1408.0, top=32.0, bottom=1440.0)   # map neatline


def lon(x):
    return 42.0 + (X0_MIN + (x - X0_PX) / PX_PER_MIN_X) / 60.0


def lat(y):
    return 18.0 + (Y0_MIN - (y - Y0_PX) / PX_PER_MIN_Y) / 60.0


def to_geo(pts):
    return [(round(lon(x), 6), round(lat(y), 6)) for x, y in pts]


# ------------------------------------------- red boundary of Rijal Almaa (poly)
# Traced clockwise in pixel space. Where the red line leaves the sheet the ring
# is closed along the neatline, so the polygon is the ON-SHEET part of the
# governorate; the notch in the south (Jabal Baqarah / gmn area) is excluded,
# exactly as the red line shows it.
RED_RING = [
    (47, 1122), (120, 1116), (170, 1110), (215, 1105),               # W edge in
    (222, 1080), (230, 1050), (240, 1020), (247, 990), (252, 960),   # W boundary
    (258, 930), (255, 900), (250, 870), (245, 840), (240, 810),
    (235, 780), (230, 750), (225, 720), (218, 690), (212, 660),
    (207, 630), (203, 605), (210, 590), (220, 575), (230, 555),
    (238, 530), (243, 500), (245, 470), (243, 440), (240, 410),
    (236, 380), (232, 350), (228, 320), (222, 285), (212, 250),
    (200, 215), (188, 180), (175, 145), (165, 113),
    (190, 116), (215, 122), (240, 132), (248, 155), (252, 180),      # N boundary
    (258, 200), (272, 215), (290, 228), (310, 232), (330, 232),
    (345, 242), (355, 258), (362, 275), (372, 290), (388, 296),
    (408, 299), (428, 302), (448, 315), (468, 330), (485, 345),
    (500, 357), (512, 368), (524, 374), (540, 376), (552, 368),
    (560, 350), (566, 330), (574, 312), (586, 300), (600, 295),
    (618, 292), (636, 291), (652, 287), (668, 288), (684, 292),
    (700, 297), (716, 302), (732, 310), (748, 320), (766, 332),
    (786, 342), (806, 352), (826, 362), (846, 372), (866, 382),
    (886, 392), (904, 400), (920, 410), (934, 422), (944, 436),
    (950, 452), (956, 466), (964, 476), (974, 486), (982, 500),
    (988, 516), (994, 532), (1002, 545), (1012, 556), (1024, 566),
    (1036, 572), (1046, 576),
    (1042, 600), (1038, 624), (1034, 648), (1032, 672), (1034, 690), # E boundary
    (1030, 706), (1032, 722), (1040, 734), (1046, 744), (1050, 760),
    (1054, 780), (1058, 800), (1062, 822), (1066, 844), (1070, 866),
    (1074, 888), (1078, 910), (1082, 932), (1086, 954), (1090, 976),
    (1094, 998), (1098, 1020), (1102, 1042), (1106, 1064), (1110, 1086),
    (1108, 1104), (1104, 1122), (1100, 1144), (1096, 1166), (1092, 1188),
    (1088, 1210), (1084, 1232), (1080, 1254), (1076, 1276), (1074, 1298),
    (1078, 1318), (1080, 1338), (1076, 1360), (1072, 1382), (1070, 1404),
    (1068, 1440),
    (745, 1440),                                                     # S neatline
    (742, 1400), (738, 1360), (730, 1326), (718, 1302), (704, 1288), # S notch
    (688, 1272), (670, 1262), (650, 1256), (628, 1252), (606, 1251),
    (584, 1250), (562, 1251), (540, 1256), (518, 1262), (496, 1267),
    (474, 1266), (452, 1264), (430, 1261), (408, 1258), (386, 1254),
    (364, 1250), (342, 1247), (320, 1246), (298, 1246),
    (295, 1440),
    (47, 1440),                                                      # S/W neatline
]


def in_ring(p, ring):
    """Ray-casting point in polygon."""
    x, y = p
    c = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xin = x1 + (y - y1) * (x2 - x1) / float(y2 - y1)
            if x < xin:
                c = not c
    return c


def inside(p):
    x, y = p
    return (FRAME['left'] <= x <= FRAME['right']
            and FRAME['top'] <= y <= FRAME['bottom']
            and in_ring(p, RED_RING))


def clip(line):
    """Clip a pixel polyline to the red polygon, keeping every inside part."""
    def cross(a, b):                      # a inside, b outside (or vice versa)
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
# The heavy black lineaments of the sheet, traced on screen. The structural
# grain is NNW-SSE (Nabitah / Red Sea escarpment trend).
FAULTS = [
    ("F01", "medium", "NNW-SSE lineament in the bb unit, SW corner of the polygon",
     [(60, 850), (90, 1000), (118, 1150), (145, 1290), (165, 1410)]),
    ("F02", "medium", "NNW-SSE lineament west of Wadi ash Shuqayq, SW corner",
     [(120, 700), (152, 860), (182, 1010), (210, 1150), (236, 1290), (255, 1400)]),
    ("F03", "low", "Short lineament near Jabal Lababah, SW corner",
     [(95, 1180), (112, 1265), (128, 1345), (140, 1420)]),
    ("F04", "high", "Long fault along the western margin of the as unit",
     [(255, 215), (292, 405), (330, 600), (366, 780), (400, 950),
      (428, 1100), (452, 1235), (470, 1350)]),
    ("F05", "high", "Fault east of F04, cutting the as / bb contact",
     [(300, 180), (340, 370), (380, 560), (416, 735), (450, 900),
      (478, 1055), (500, 1200), (516, 1320)]),
    ("F06", "high", "Western margin of the cross-hatched band inside the as unit",
     [(430, 55), (466, 240), (500, 420), (536, 610), (570, 800),
      (600, 965), (625, 1120), (645, 1250)]),
    ("F07", "high", "Eastern margin of the cross-hatched band inside the as unit",
     [(465, 50), (503, 235), (540, 420), (576, 612), (610, 800),
      (640, 970), (665, 1130), (685, 1260)]),
    ("F08", "high", "Fault on the eastern margin of the as unit against bt",
     [(560, 60), (596, 242), (630, 420), (666, 608), (700, 790),
      (730, 960), (755, 1120), (775, 1250)]),
    ("F09", "medium", "NNW-SSE fault through the jt / bt units",
     [(610, 45), (646, 230), (680, 410), (715, 598), (748, 780),
      (776, 950), (800, 1110), (818, 1240)]),
    ("F10", "medium", "NNW-SSE fault east of F09",
     [(665, 45), (700, 225), (732, 400), (764, 582), (795, 760),
      (822, 925), (845, 1080), (862, 1210)]),
    ("F11", "medium", "NNW-SSE fault west of Wadi al Marabi",
     [(740, 40), (773, 218), (805, 395), (837, 575), (868, 750),
      (894, 910), (918, 1060), (935, 1190)]),
    ("F12", "medium", "NNW-SSE fault in the bt unit, Wadi al Marabi corridor",
     [(800, 45), (832, 218), (862, 390), (892, 565), (922, 740),
      (947, 895), (970, 1040), (988, 1170)]),
    ("F13", "medium", "NNW-SSE fault east of Wadi al Marabi",
     [(880, 50), (910, 220), (940, 390), (970, 562), (998, 730),
      (1022, 880), (1044, 1020), (1060, 1140)]),
    ("F14", "medium", "NNW-SSE fault approaching the eastern red boundary",
     [(955, 60), (984, 228), (1012, 395), (1041, 565), (1068, 730),
      (1092, 878), (1112, 1010)]),
    ("F15", "low", "Fault segment close to the eastern red boundary",
     [(1010, 55), (1038, 222), (1065, 390), (1092, 558), (1118, 720)]),
    ("F16", "low", "Short lineament in the northern part of the polygon",
     [(960, 120), (978, 210), (995, 300), (1010, 385)]),
    ("F17", "low", "Short lineament in the central bt unit",
     [(860, 430), (876, 525), (892, 620), (906, 710)]),
    ("F18", "low", "Short lineament in the south-central part of the polygon",
     [(760, 1180), (778, 1270), (794, 1350), (806, 1420)]),
    ("F19", "medium", "NNW-SSE lineament in the SW part, bb / Qal contact zone",
     [(200, 1150), (222, 1250), (240, 1330), (256, 1410)]),
    ("F20", "low", "Short lineament between F04 and F05, northern polygon",
     [(276, 250), (300, 370), (322, 490), (342, 600)]),
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
    dx = math.radians(x2 - x1) * math.cos(m)
    dy = math.radians(y2 - y1)
    return (math.degrees(math.atan2(dx, dy)) + 360.0) % 180.0


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
    """Shoelace on a sinusoidal projection about the ring centroid."""
    R = 6371008.8
    lat0 = sum(p[1] for p in ring_geo) / len(ring_geo)
    lon0 = sum(p[0] for p in ring_geo) / len(ring_geo)
    pts = [(R * math.radians(a - lon0) * math.cos(math.radians(b)),
            R * math.radians(b - lat0)) for a, b in ring_geo]
    s = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0 / 1e6


# --------------------------------------------------------------- study area shp
ring_geo = to_geo([(float(a), float(b)) for a, b in RED_RING])
AREA = area_km2(ring_geo)
PERIM = geod_len_m(ring_geo + [ring_geo[0]]) / 1000.0

sbase = os.path.join(OUT, "study_area_sheet2")
sw = shapefile.Writer(sbase, shapeType=shapefile.POLYGON)
sw.field("FID", "N", 6, 0)
sw.field("NAME", "C", 70)
sw.field("AREA_KM2", "N", 14, 3)
sw.field("PERIM_KM", "N", 14, 3)
sw.field("NOTE", "C", 120)
# shapefile polygon outer ring must be clockwise in x/y (lon/lat) order
ring = [list(p) for p in ring_geo]
def signed(r):
    return sum((r[i][0] * r[(i + 1) % len(r)][1] - r[(i + 1) % len(r)][0] * r[i][1])
               for i in range(len(r)))
if signed(ring) > 0:
    ring.reverse()
sw.poly([ring + [ring[0]]])
sw.record(1, "Rijal Almaa Governorate - on-sheet part (sheet 42E)",
          round(AREA, 3), round(PERIM, 3),
          "On-sheet portion only; the polygon is closed along the map neatline "
          "where the red line leaves the sheet")
sw.close()
write_prj(sbase)

# ------------------------------------------------------------------ faults shp
base = os.path.join(OUT, "faults_sheet2")
w = shapefile.Writer(base, shapeType=shapefile.POLYLINE)
w.field("FID", "N", 6, 0)
w.field("NAME", "C", 20)
w.field("FEATURE", "C", 30)
w.field("TREND", "C", 12)
w.field("STRIKE_DEG", "N", 8, 1)
w.field("LENGTH_M", "N", 12, 1)
w.field("CONF", "C", 10)
w.field("METHOD", "C", 45)
w.field("SOURCE", "C", 60)
w.field("NOTE", "C", 120)

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
           "features": feats},
          open(base + ".geojson", "w"), indent=1)

# --------------------------------------------------------------- preview (SVG)
o = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
     'viewBox="0 0 %d %d">' % (IMG_W, IMG_H, IMG_W, IMG_H),
     '<rect width="100%%" height="100%%" fill="#fdfaf5"/>']
for m in range(0, 30, 5):
    x = X0_PX + m * PX_PER_MIN_X
    if x > FRAME['right']:
        continue
    o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#e8863c" '
             'stroke-width="1"/>' % (x, FRAME['top'], x, FRAME['bottom']))
    o.append('<text x="%.1f" y="%.1f" font-size="21" text-anchor="middle" '
             'fill="#8a5a2b">42%s%s</text>'
             % (x, FRAME['bottom'] + 28, chr(176), "" if m == 0 else "%d'" % m))
for m in range(0, 30, 5):
    y = Y0_PX + (Y0_MIN - m) * PX_PER_MIN_Y
    if not (FRAME['top'] <= y <= FRAME['bottom']):
        continue
    o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#e8863c" '
             'stroke-width="1"/>' % (FRAME['left'], y, FRAME['right'], y))
    o.append('<text x="%.1f" y="%.1f" font-size="21" fill="#8a5a2b">18%s%s</text>'
             % (FRAME['right'] + 8, y + 7, chr(176), "" if m == 0 else "%d'" % m))
o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="none" '
         'stroke="#222" stroke-width="2.5"/>'
         % (FRAME['left'], FRAME['top'], FRAME['right'] - FRAME['left'],
            FRAME['bottom'] - FRAME['top']))
o.append('<polygon fill="#e01b1b" fill-opacity="0.08" stroke="#e01b1b" '
         'stroke-width="7" stroke-linejoin="round" points="%s"/>'
         % " ".join("%.1f,%.1f" % p for p in RED_RING))
for part in preview_px:
    o.append('<polyline fill="none" stroke="#12261a" stroke-width="4" '
             'stroke-linecap="round" points="%s"/>'
             % " ".join("%.1f,%.1f" % p for p in part))
o.append('<text x="60" y="1500" font-size="26" fill="#222">Sheet 42E - faults '
         'clipped to the red Rijal Almaa polygon (%.1f km2) - visual '
         'interpretation QC overlay</text>' % AREA)
o.append('</svg>')
open(os.path.join(OUT, "preview_sheet2.svg"), "w").write("\n".join(o))

print("study area: %.2f km2, perimeter %.2f km" % (AREA, PERIM))
print("fault features: %d" % fid)
tot = 0.0
for r in shapefile.Reader(base).records():
    tot += r[5]
    print("  %-8s %-9s strike %5.1f  len %8.0f m  %s" % (r[1], r[3], r[4], r[5], r[6]))
print("total fault length: %.2f km" % (tot / 1000.0))
print("bbox:", [round(v, 5) for v in shapefile.Reader(base).bbox])
