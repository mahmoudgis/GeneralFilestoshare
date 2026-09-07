# -*- coding: utf-8 -*-
"""Sheet 1 (41 52.5'-42 00.2'E): the red boundary as a POLYGON, so the three
sheets can be summed. Same georeference as build_faults.py."""
import math, os, shapefile

OUT = os.path.dirname(os.path.abspath(__file__))
X0_PX, X0_MIN, PXX = 175.0, 53.0, 232.0
Y0_PX, Y0_MIN, PXY = 115.0, 6.0, 229.3
FRAME = dict(left=68.0, right=1838.0, top=62.0, bottom=1560.0)

lon = lambda x: 41.0 + (X0_MIN + (x - X0_PX) / PXX) / 60.0
lat = lambda y: 18.0 + (Y0_MIN - (y - Y0_PX) / PXY) / 60.0

# red line across the sheet, extended to both neatline edges, then closed
# clockwise around the SE (governorate) side of it
RING = ([(68, 1256), (420, 1188), (575, 1218), (1105, 358), (1232, 228),
         (1545, 222), (1810, 160), (1838, 153)]
        + [(1838, 1560), (68, 1560)])
ring_geo = [(round(lon(x), 6), round(lat(y), 6)) for x, y in RING]


def area_km2(r):
    R = 6371008.8
    la = sum(p[1] for p in r) / len(r)
    lo = sum(p[0] for p in r) / len(r)
    p = [(R * math.radians(a - lo) * math.cos(math.radians(b)),
          R * math.radians(b - la)) for a, b in r]
    return abs(sum(x1 * y2 - x2 * y1
                   for (x1, y1), (x2, y2) in zip(p, p[1:] + p[:1]))) / 2e6


def perim_km(r):
    R = 6371008.8
    t = 0.0
    for (x1, y1), (x2, y2) in zip(r, r[1:] + r[:1]):
        m = math.radians((y1 + y2) / 2.0)
        t += R * math.hypot(math.radians(x2 - x1) * math.cos(m),
                            math.radians(y2 - y1))
    return t / 1000.0


A, P = area_km2(ring_geo), perim_km(ring_geo)
base = os.path.join(OUT, "study_area_sheet1")
w = shapefile.Writer(base, shapeType=shapefile.POLYGON)
w.field("FID", "N", 6, 0)
w.field("NAME", "C", 70)
w.field("AREA_KM2", "N", 14, 3)
w.field("PERIM_KM", "N", 14, 3)
w.field("NOTE", "C", 150)
ring = [list(p) for p in ring_geo]
if sum(ring[i][0] * ring[(i + 1) % len(ring)][1]
       - ring[(i + 1) % len(ring)][0] * ring[i][1] for i in range(len(ring))) > 0:
    ring.reverse()
w.poly([ring + [ring[0]]])
w.record(1, "Rijal Almaa Governorate - on-sheet part (sheet 41E)",
         round(A, 3), round(P, 3),
         "On-sheet portion only, closed along the map neatline; the whole "
         "on-sheet polygon carries mapped geology")
w.close()
open(base + ".prj", "w").write(
    'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,'
    '298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]')
open(base + ".cpg", "w").write("UTF-8")
print("sheet 1 on-sheet polygon: %.2f km2, perimeter %.2f km" % (A, P))
