# -*- coding: utf-8 -*-
"""
Visual (on-screen) digitising of fault / lineament traces from the scanned
USGS geologic sheet (Wadi Nadi - Jibal ash Shams area, 41 52'-42 00'E,
17 59.7'-18 06.2'N), restricted to the area SE of the red administrative
boundary of Rijal Almaa Governorate (mahafazat Rijal Alma').

Digitising is done in the pixel space of the supplied map image and converted
to WGS84 geographic coordinates with the affine model fitted to the printed
graticule ticks.

Outputs (EPSG:4326):
    faults_rijal_almaa.shp     - digitised fault / lineament traces (polyline)
    study_area_boundary.shp    - the red boundary line used for clipping
    faults_rijal_almaa.geojson - same faults, GeoJSON
    preview.svg                - QC overlay in the original image pixel frame
"""
import json, math, os
import shapefile  # pyshp

OUT = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- georeference
# graticule control points read off the printed ticks of the supplied image
# (image size ~1907 x 1919 px)
X0_PX, X0_MIN = 175.0, 53.0      # 41 deg 53' meridian
PX_PER_MIN_X = 232.0             # (42 00' at x = 1799 px)
Y0_PX, Y0_MIN = 115.0, 6.0       # 18 deg 06' parallel
PX_PER_MIN_Y = 229.3             # (17 59' at y = 1718 px)

IMG_W, IMG_H = 1907, 1919
FRAME = dict(left=68.0, right=1838.0, top=62.0, bottom=1560.0)   # map neatline


def lon(x):
    return 41.0 + (X0_MIN + (x - X0_PX) / PX_PER_MIN_X) / 60.0


def lat(y):
    return 18.0 + (Y0_MIN - (y - Y0_PX) / PX_PER_MIN_Y) / 60.0


def to_geo(pts):
    return [(round(lon(x), 6), round(lat(y), 6)) for x, y in pts]


# ------------------------------------------------- red administrative boundary
# vertices of the red line (legend: mahafazat Rijal Alma'), pixel space
RED = [(60.0, 1258.0), (420.0, 1188.0), (575.0, 1218.0), (1105.0, 358.0),
       (1232.0, 228.0), (1545.0, 222.0), (1810.0, 160.0)]


def red_y(x):
    """y of the red boundary at a given x (extrapolated flat outside range)."""
    if x <= RED[0][0]:
        return RED[0][1]
    if x >= RED[-1][0]:
        return RED[-1][1]
    for (x1, y1), (x2, y2) in zip(RED, RED[1:]):
        if x1 <= x <= x2:
            t = (x - x1) / (x2 - x1)
            return y1 + t * (y2 - y1)
    return RED[-1][1]


def inside(p):
    """True when the pixel lies SE of the red line and inside the neatline."""
    x, y = p
    return (y > red_y(x)
            and FRAME['left'] <= x <= FRAME['right']
            and FRAME['top'] <= y <= FRAME['bottom'])


def _f(p):
    """signed 'insideness' used for interpolating the crossing point."""
    x, y = p
    return min(y - red_y(x), x - FRAME['left'], FRAME['right'] - x,
               y - FRAME['top'], FRAME['bottom'] - y)


def clip(line):
    """Clip a pixel polyline to the study area, keeping every inside part."""
    parts, cur = [], []
    for a, b in zip(line, line[1:]):
        ia, ib = inside(a), inside(b)
        if ia:
            if not cur:
                cur.append(a)
            cur.append(b) if ib else None
        if ia != ib:                                   # crossing -> bisect
            lo, hi = (a, b) if ia else (b, a)          # lo inside, hi outside
            for _ in range(40):
                mid = ((lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0)
                if _f(mid) > 0:
                    lo = mid
                else:
                    hi = mid
            if ia:
                cur.append(lo)
                parts.append(cur)
                cur = []
            else:
                cur = [lo, b]
    if inside(line[-1]) and cur and cur[-1] != line[-1]:
        cur.append(line[-1])
    if cur:
        parts.append(cur)
    return [p for p in parts if len(p) >= 2]


# --------------------------------------------------------- digitised lineaments
# name, confidence, note, vertices (pixel space of the supplied image)
FAULTS = [
    ("F01", "medium",
     "N-S trace in the SW strip of the study area, west of Wadi ash Shuqayq",
     [(326, 1218), (338, 1300), (350, 1400), (360, 1500), (367, 1558)]),
    ("F02", "medium",
     "N-S trace passing close to the 7 dip symbol, SW strip",
     [(418, 1196), (432, 1290), (444, 1390), (456, 1490), (464, 1558)]),
    ("F03", "high",
     "Long N-S trace west of Wadi ash Shuqayq, cut by the red boundary at its kink",
     [(566, 1216), (574, 1290), (582, 1370), (590, 1455), (599, 1558)]),
    ("F04", "medium",
     "Short N-S splay parallel to F03",
     [(688, 1232), (700, 1315), (713, 1400), (726, 1490), (737, 1558)]),
    ("F05", "high",
     "N-S trace passing just west of the 55 dip symbol",
     [(790, 1176), (798, 1275), (805, 1375), (811, 1470), (816, 1558)]),
    ("F06", "medium",
     "N-S trace in the dotted granite (gt) unit, south-central sheet",
     [(864, 1086), (876, 1195), (886, 1310), (895, 1430), (902, 1558)]),
    ("F07", "high",
     "Principal N-S fault of the SE sector, traced from the red boundary to the "
     "southern neatline near the 41 57' meridian",
     [(1084, 372), (1078, 520), (1072, 680), (1064, 850), (1056, 1030),
      (1049, 1220), (1044, 1400), (1040, 1558)]),
    ("F08", "high",
     "N-S to NNW-SSE trace east of F07, dies out in the granite before the "
     "southern edge",
     [(1148, 226), (1163, 380), (1177, 540), (1191, 710), (1205, 890),
      (1216, 1050), (1222, 1160)]),
    ("F09", "medium",
     "Short N-S to NNW-SSE trace, Jibal ash Shams southern slope",
     [(1298, 232), (1310, 370), (1322, 510), (1332, 650), (1339, 762)]),
    ("F10", "medium",
     "N-S to NNW-SSE trace west of Wadi Nadi",
     [(1426, 236), (1443, 380), (1458, 520), (1472, 665), (1483, 800)]),
    ("F11", "medium",
     "N-S to NNW-SSE trace on the eastern flank of Jibal ash Shams",
     [(1558, 228), (1573, 370), (1586, 505), (1598, 640), (1607, 760)]),
    ("F12", "low",
     "Easternmost trace near the sheet margin, poorly defined on the scan",
     [(1688, 244), (1701, 380), (1712, 510), (1721, 630), (1727, 742)]),
]

BOUNDARY_NAME = "Rijal Almaa Governorate boundary (red line)"


# ------------------------------------------------------------------ geometry
def geod_len_m(pts):
    """Length in metres of a lon/lat polyline (equirectangular approximation)."""
    R = 6371008.8
    tot = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        m = math.radians((y1 + y2) / 2.0)
        dx = math.radians(x2 - x1) * math.cos(m)
        dy = math.radians(y2 - y1)
        tot += R * math.hypot(dx, dy)
    return tot


def strike_deg(pts):
    """Mean azimuth of the trace, folded to 0-180 (geological strike)."""
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    m = math.radians((y1 + y2) / 2.0)
    dx = math.radians(x2 - x1) * math.cos(m)
    dy = math.radians(y2 - y1)
    az = (math.degrees(math.atan2(dx, dy)) + 360.0) % 180.0
    return az


def trend_name(s):
    for lo, hi, nm in ((0, 11.25, "N-S"), (11.25, 33.75, "NNE-SSW"),
                       (33.75, 56.25, "NE-SW"), (56.25, 78.75, "ENE-WSW"),
                       (78.75, 101.25, "E-W"), (101.25, 123.75, "WNW-ESE"),
                       (123.75, 146.25, "NW-SE"), (146.25, 168.75, "NNW-SSE"),
                       (168.75, 180.01, "N-S")):
        if lo <= s < hi:
            return nm
    return "N-S"


PRJ = ('GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",'
       'SPHEROID["WGS_1984",6378137.0,298.257223563]],'
       'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]')


def write_prj(base):
    with open(base + ".prj", "w") as f:
        f.write(PRJ)
    with open(base + ".cpg", "w") as f:
        f.write("UTF-8")


# ------------------------------------------------------------------- faults shp
base = os.path.join(OUT, "faults_rijal_almaa")
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

records, geo_features, preview_px = [], [], []
fid = 0
for name, conf, note, px in FAULTS:
    for k, part in enumerate(clip([(float(a), float(b)) for a, b in px])):
        fid += 1
        g = to_geo(part)
        s = strike_deg(g)
        w.line([[list(p) for p in g]])
        w.record(fid,
                 name if k == 0 else "%s_%d" % (name, k + 1),
                 "Fault / lineament",
                 trend_name(s), round(s, 1), round(geod_len_m(g), 1),
                 conf,
                 "Visual interpretation (on-screen digitising)",
                 "Scanned USGS geologic map sheet, Dar Al Asfahani print",
                 note)
        preview_px.append(part)
        geo_features.append({
            "type": "Feature",
            "properties": {"FID": fid, "NAME": name, "FEATURE": "Fault / lineament",
                           "TREND": trend_name(s), "STRIKE_DEG": round(s, 1),
                           "LENGTH_M": round(geod_len_m(g), 1), "CONF": conf,
                           "METHOD": "Visual interpretation (on-screen digitising)",
                           "NOTE": note},
            "geometry": {"type": "LineString", "coordinates": [list(p) for p in g]}})
w.close()
write_prj(base)

with open(base + ".geojson", "w") as f:
    json.dump({"type": "FeatureCollection",
               "crs": {"type": "name",
                       "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
               "features": geo_features}, f, indent=1)

# ---------------------------------------------------------------- boundary shp
bbase = os.path.join(OUT, "study_area_boundary")
b = shapefile.Writer(bbase, shapeType=shapefile.POLYLINE)
b.field("FID", "N", 6, 0)
b.field("NAME", "C", 60)
b.field("SIDE", "C", 40)
b.line([[list(p) for p in to_geo(RED)]])
b.record(1, BOUNDARY_NAME, "faults digitised on the SE side")
b.close()
write_prj(bbase)

# --------------------------------------------------------------- preview (SVG)
def svg():
    o = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
         'viewBox="0 0 %d %d">' % (IMG_W, IMG_H, IMG_W, IMG_H),
         '<rect width="100%%" height="100%%" fill="#fdfaf5"/>']
    # graticule
    for m in range(53, 61):
        x = X0_PX + (m - X0_MIN) * PX_PER_MIN_X
        o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#e8863c" '
                 'stroke-width="1.2"/>' % (x, FRAME['top'], x, FRAME['bottom']))
        o.append('<text x="%.1f" y="%.1f" font-size="26" text-anchor="middle" '
                 'fill="#8a5a2b">%s</text>'
                 % (x, FRAME['bottom'] + 34, ("42%s" % chr(176)) if m == 60
                    else ("41%s%d\'" % (chr(176), m))))
    for m in range(0, 7):
        y = Y0_PX + (Y0_MIN - m) * PX_PER_MIN_Y
        o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#e8863c" '
                 'stroke-width="1.2"/>' % (FRAME['left'], y, FRAME['right'], y))
        o.append('<text x="%.1f" y="%.1f" font-size="26" fill="#8a5a2b">18%s%d\''
                 '</text>' % (FRAME['right'] + 10, y + 9, chr(176), m))
    o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="none" '
             'stroke="#222" stroke-width="3"/>'
             % (FRAME['left'], FRAME['top'], FRAME['right'] - FRAME['left'],
                FRAME['bottom'] - FRAME['top']))
    o.append('<polyline fill="none" stroke="#e01b1b" stroke-width="14" '
             'stroke-linejoin="round" points="%s"/>'
             % " ".join("%.1f,%.1f" % p for p in RED))
    for part in preview_px:
        o.append('<polyline fill="none" stroke="#1b3a1b" stroke-width="5" '
                 'stroke-linecap="round" points="%s"/>'
                 % " ".join("%.1f,%.1f" % p for p in part))
    o.append('<text x="80" y="1640" font-size="30" fill="#222">Digitised faults '
             '(SE of the red boundary) - visual interpretation QC overlay</text>')
    o.append('</svg>')
    return "\n".join(o)


with open(os.path.join(OUT, "preview.svg"), "w") as f:
    f.write(svg())

print("features written:", fid)
for r in shapefile.Reader(base).records():
    print("  %-8s %-9s strike %5.1f  len %7.0f m  %s" % (r[1], r[3], r[4], r[5], r[6]))
r = shapefile.Reader(base)
print("bbox:", [round(v, 5) for v in r.bbox])
