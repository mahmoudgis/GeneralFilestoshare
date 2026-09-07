# -*- coding: utf-8 -*-
"""Merge the four sheets into one fault shapefile, one study-area shapefile and
one dissolved study-area polygon, and report de-duplicated totals."""
import json, math, os, shapefile
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.dirname(os.path.abspath(__file__))
PRJ = ('GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,'
       '298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]')

SHEETS = [
    ("41E-north", "41 52.5'-42 00.2'E, 17 59.7'-18 06.2'N",
     "faults_rijal_almaa/faults_rijal_almaa", "faults_rijal_almaa/study_area_sheet1"),
    ("42E-north", "42 00'-42 28'E, 17 59.7'-18 28'N",
     "faults_rijal_almaa_sheet2/faults_sheet2", "faults_rijal_almaa_sheet2/study_area_sheet2"),
    ("42E-south", "42 00'-42 23.3'E, 17 46.5'-18 11.9'N",
     "faults_rijal_almaa_sheet3/faults_sheet3", "faults_rijal_almaa_sheet3/study_area_sheet3"),
    ("41E-coast", "41 46'-42 03.8'E, 17 42.5'-18 01.3'N",
     "faults_rijal_almaa_sheet4/faults_sheet4", "faults_rijal_almaa_sheet4/study_area_sheet4"),
]

R = 6371008.8


def eq_area(geom, lat0, lon0):
    """Project lon/lat -> metres (sinusoidal about lat0/lon0) for area work."""
    def f(pts):
        return [(R * math.radians(a - lon0) * math.cos(math.radians(b)),
                 R * math.radians(b - lat0)) for a, b in pts]
    return Polygon(f(geom.exterior.coords))


# ------------------------------------------------------------- merged faults
base = os.path.join(OUT, "faults_rijal_almaa_all")
w = shapefile.Writer(base, shapeType=shapefile.POLYLINE)
for f, t, sz, d in (("FID", "N", 6, 0), ("SHEET", "C", 12, 0), ("NAME", "C", 20, 0),
                    ("FEATURE", "C", 30, 0), ("TREND", "C", 12, 0),
                    ("STRIKE_DEG", "N", 8, 1), ("LENGTH_M", "N", 12, 1),
                    ("CONF", "C", 10, 0), ("METHOD", "C", 45, 0),
                    ("SOURCE", "C", 60, 0), ("NOTE", "C", 120, 0)):
    w.field(f, t, sz, d) if t == "N" else w.field(f, t, sz)

fid, per_sheet, feats, lines = 0, {}, [], []
for sheet, _, fpath, _ in SHEETS:
    r = shapefile.Reader(os.path.join(ROOT, fpath))
    flds = [f[0] for f in r.fields[1:]]
    tot = 0.0
    for sh, rec in zip(r.shapes(), r.records()):
        fid += 1
        d = dict(zip(flds, list(rec)))
        pts = [list(p) for p in sh.points]
        w.line([pts])
        w.record(fid, sheet, d["NAME"], d["FEATURE"], d["TREND"], d["STRIKE_DEG"],
                 d["LENGTH_M"], d["CONF"], d["METHOD"], d["SOURCE"], d["NOTE"])
        tot += d["LENGTH_M"]
        lines.append((sheet, d["NAME"], LineString(pts)))
        feats.append({"type": "Feature",
                      "properties": {"FID": fid, "SHEET": sheet, "NAME": d["NAME"],
                                     "FEATURE": d["FEATURE"], "TREND": d["TREND"],
                                     "STRIKE_DEG": d["STRIKE_DEG"],
                                     "LENGTH_M": d["LENGTH_M"], "CONF": d["CONF"],
                                     "NOTE": d["NOTE"]},
                      "geometry": {"type": "LineString", "coordinates": pts}})
    per_sheet[sheet] = (len(r), tot / 1000.0)
w.close()
open(base + ".prj", "w").write(PRJ)
open(base + ".cpg", "w").write("UTF-8")
json.dump({"type": "FeatureCollection",
           "crs": {"type": "name",
                   "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
           "features": feats}, open(base + ".geojson", "w"), indent=1)

# ---------------------------------------------------- duplicate-trace check
DUP_M = 400.0
dups = []
for i in range(len(lines)):
    for j in range(i + 1, len(lines)):
        if lines[i][0] == lines[j][0]:
            continue
        d = lines[i][2].distance(lines[j][2]) * 111000.0
        if d < DUP_M:
            dups.append((lines[i][0], lines[i][1], lines[j][0], lines[j][1], d))

# --------------------------------------------------------- merged study areas
sbase = os.path.join(OUT, "study_area_all")
sw = shapefile.Writer(sbase, shapeType=shapefile.POLYGON)
for f, t, sz, d in (("FID", "N", 6, 0), ("SHEET", "C", 12, 0), ("EXTENT", "C", 45, 0),
                    ("NAME", "C", 70, 0), ("AREA_KM2", "N", 14, 3),
                    ("GEOL_KM2", "N", 14, 3), ("PERIM_KM", "N", 14, 3)):
    sw.field(f, t, sz, d) if t == "N" else sw.field(f, t, sz)

areas, polys = {}, []
for i, (sheet, extent, _, spath) in enumerate(SHEETS, 1):
    r = shapefile.Reader(os.path.join(ROOT, spath))
    flds = [f[0] for f in r.fields[1:]]
    d = dict(zip(flds, list(r.record(0))))
    geol = d.get("GEOL_KM2", d["AREA_KM2"])
    pts = [list(p) for p in r.shape(0).points]
    sw.poly([pts])
    sw.record(i, sheet, extent, d["NAME"], d["AREA_KM2"], geol, d["PERIM_KM"])
    areas[sheet] = (d["AREA_KM2"], geol)
    polys.append(Polygon(pts).buffer(0))
sw.close()
open(sbase + ".prj", "w").write(PRJ)
open(sbase + ".cpg", "w").write("UTF-8")

# ------------------------------------------- dissolved (de-duplicated) polygon
u = unary_union(polys)
geoms = list(u.geoms) if u.geom_type == "MultiPolygon" else [u]
lat0 = u.centroid.y
lon0 = u.centroid.x
UNION_KM2 = sum(eq_area(g, lat0, lon0).area for g in geoms) / 1e6

dbase = os.path.join(OUT, "study_area_dissolved")
dw = shapefile.Writer(dbase, shapeType=shapefile.POLYGON)
for f, t, sz, d in (("FID", "N", 6, 0), ("NAME", "C", 70, 0),
                    ("AREA_KM2", "N", 14, 3), ("NOTE", "C", 150, 0)):
    dw.field(f, t, sz, d) if t == "N" else dw.field(f, t, sz)
parts = []
for g in geoms:
    ext = list(g.exterior.coords)
    if sum(ext[i][0] * ext[i + 1][1] - ext[i + 1][0] * ext[i][1]
           for i in range(len(ext) - 1)) > 0:
        ext.reverse()
    parts.append([list(p) for p in ext])
    for ring in g.interiors:
        ir = list(ring.coords)
        if sum(ir[i][0] * ir[i + 1][1] - ir[i + 1][0] * ir[i][1]
               for i in range(len(ir) - 1)) < 0:
            ir.reverse()
        parts.append([list(p) for p in ir])
dw.poly(parts)
dw.record(1, "Rijal Almaa Governorate - union of the four map sheets",
          round(UNION_KM2, 3),
          "Union of the four on-sheet polygons, overlaps removed; still only "
          "the part covered by the four sheets, not the whole governorate")
dw.close()
open(dbase + ".prj", "w").write(PRJ)
open(dbase + ".cpg", "w").write("UTF-8")

# ------------------------------- union restricted to the mapped-geology area
# sheets 1 and 2 are fully covered; sheet 3 has geology only south of 18 00';
# sheet 4 only west of 42 01.1', and north of 18 00' only west of 42 00'.
GEOL_MASK = {
    "42E-south": box(41.9, 17.5, 42.5, 18.0),
    "41E-coast": box(41.6, 17.5, 42.0, 18.2).union(box(41.6, 17.5, 42.0185, 18.0)),
}
gp = []
for (sheet, _, _, _), poly in zip(SHEETS, polys):
    m = GEOL_MASK.get(sheet)
    gp.append(poly.intersection(m) if m is not None else poly)
gu = unary_union(gp)
gg = list(gu.geoms) if gu.geom_type == "MultiPolygon" else [gu]
GEOL_UNION_KM2 = sum(eq_area(g, lat0, lon0).area for g in gg) / 1e6

# ------------------------------------------------------------------- report
print("%-11s %5s %11s %11s %11s  %s"
      % ("sheet", "n", "length_km", "area_km2", "geol_km2", "extent"))
tn = tl = ta = tg = 0
for sheet, extent, _, _ in SHEETS:
    n, L = per_sheet[sheet]
    A, G = areas[sheet]
    tn += n; tl += L; ta += A; tg += G
    print("%-11s %5d %11.2f %11.2f %11.2f  %s" % (sheet, n, L, A, G, extent))
print("%-11s %5d %11.2f %11.2f %11.2f  (naive sum, sheets overlap)"
      % ("TOTAL", tn, tl, ta, tg))
print()
print("dissolved union of the four polygons: %.2f km2 "
      "(overlap removed: %.2f km2)" % (UNION_KM2, ta - UNION_KM2))
print("union parts: %d ring(s) in %d polygon(s)" % (len(parts), len(geoms)))
print("union restricted to mapped geology: %.2f km2" % GEOL_UNION_KM2)
print("total fault length: %.2f km -> %.3f km/km2 over the whole union, "
      "%.3f km/km2 over the mapped-geology union"
      % (tl, tl / UNION_KM2, tl / GEOL_UNION_KM2))
print("duplicate traces across sheets (< %d m apart): %d" % (DUP_M, len(dups)))
for a in dups:
    print("   %s/%s  vs  %s/%s  %.0f m" % a)
print("merged bbox:", [round(v, 5) for v in shapefile.Reader(base).bbox])
