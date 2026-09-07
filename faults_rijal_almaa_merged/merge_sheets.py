# -*- coding: utf-8 -*-
"""Merge the three sheets into one fault layer and one study-area layer."""
import json, math, os, shapefile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.dirname(os.path.abspath(__file__))
PRJ = ('GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,'
       '298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]')

SHEETS = [("41E",      "faults_rijal_almaa/faults_rijal_almaa",
                       "faults_rijal_almaa/study_area_sheet1"),
          ("42E-north", "faults_rijal_almaa_sheet2/faults_sheet2",
                        "faults_rijal_almaa_sheet2/study_area_sheet2"),
          ("42E-south", "faults_rijal_almaa_sheet3/faults_sheet3",
                        "faults_rijal_almaa_sheet3/study_area_sheet3")]

# ---------------------------------------------------------------------- faults
base = os.path.join(OUT, "faults_all_sheets")
w = shapefile.Writer(base, shapeType=shapefile.POLYLINE)
w.field("FID", "N", 6, 0)
w.field("SHEET", "C", 12)
w.field("NAME", "C", 20)
w.field("FEATURE", "C", 30)
w.field("TREND", "C", 12)
w.field("STRIKE_DEG", "N", 8, 1)
w.field("LENGTH_M", "N", 12, 1)
w.field("CONF", "C", 10)
w.field("METHOD", "C", 45)
w.field("NOTE", "C", 120)

fid, per_sheet, feats = 0, {}, []
for sheet, fpath, _ in SHEETS:
    r = shapefile.Reader(os.path.join(ROOT, fpath))
    flds = [f[0] for f in r.fields[1:]]
    tot = 0.0
    for sh, rec in zip(r.shapes(), r.records()):
        fid += 1
        d = dict(zip(flds, list(rec)))
        pts = [list(p) for p in sh.points]
        w.line([pts])
        w.record(fid, sheet, d["NAME"], d["FEATURE"], d["TREND"],
                 d["STRIKE_DEG"], d["LENGTH_M"], d["CONF"], d["METHOD"], d["NOTE"])
        tot += d["LENGTH_M"]
        feats.append({"type": "Feature",
                      "properties": {"FID": fid, "SHEET": sheet, "NAME": d["NAME"],
                                     "TREND": d["TREND"], "STRIKE_DEG": d["STRIKE_DEG"],
                                     "LENGTH_M": d["LENGTH_M"], "CONF": d["CONF"]},
                      "geometry": {"type": "LineString", "coordinates": pts}})
    per_sheet[sheet] = (len(r), tot / 1000.0)
w.close()
open(base + ".prj", "w").write(PRJ)
open(base + ".cpg", "w").write("UTF-8")
json.dump({"type": "FeatureCollection",
           "crs": {"type": "name",
                   "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
           "features": feats}, open(base + ".geojson", "w"), indent=1)

# ----------------------------------------------------------------- study areas
sbase = os.path.join(OUT, "study_area_all_sheets")
sw = shapefile.Writer(sbase, shapeType=shapefile.POLYGON)
sw.field("FID", "N", 6, 0)
sw.field("SHEET", "C", 12)
sw.field("NAME", "C", 70)
sw.field("AREA_KM2", "N", 14, 3)
sw.field("GEOL_KM2", "N", 14, 3)
sw.field("PERIM_KM", "N", 14, 3)

areas = {}
for i, (sheet, _, spath) in enumerate(SHEETS, 1):
    r = shapefile.Reader(os.path.join(ROOT, spath))
    flds = [f[0] for f in r.fields[1:]]
    d = dict(zip(flds, list(r.record(0))))
    geol = d.get("GEOL_KM2", d["AREA_KM2"])
    sw.poly([[list(p) for p in r.shape(0).points]])
    sw.record(i, sheet, d["NAME"], d["AREA_KM2"], geol, d["PERIM_KM"])
    areas[sheet] = (d["AREA_KM2"], geol)
sw.close()
open(sbase + ".prj", "w").write(PRJ)
open(sbase + ".cpg", "w").write("UTF-8")

print("%-11s %6s %12s %12s %12s" % ("sheet", "n", "length_km", "area_km2", "geol_km2"))
tn = tl = ta = tg = 0
for sheet, _, _ in SHEETS:
    n, L = per_sheet[sheet]
    A, G = areas[sheet]
    tn += n; tl += L; ta += A; tg += G
    print("%-11s %6d %12.2f %12.2f %12.2f" % (sheet, n, L, A, G))
print("%-11s %6d %12.2f %12.2f %12.2f" % ("TOTAL", tn, tl, ta, tg))
print("fault density over the geology-covered study area: %.3f km/km2" % (tl / tg))
b = shapefile.Reader(base).bbox
print("merged bbox:", [round(v, 5) for v in b])
