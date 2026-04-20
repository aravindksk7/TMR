"""
build_p1_layout.py
Generates P1 | CXO Quality Dashboard layout and injects it into the PBIX file.
Canvas: 1280 x 720

ETMI = (Automation Coverage % × 0.4) + (Regression Automation % × 0.3) + (Execution Efficiency % × 0.3)
"""
import json
import shutil
import sys
import zipfile
import os
import uuid
from pathlib import Path

PBIX_IN  = r"C:\TM_PBI\qa_pipeline\QA-Pipeline-Report.pbix"
PBIX_OUT = r"C:\TM_PBI\qa_pipeline\QA-Pipeline-Report.pbix"

VIEW  = "vw_p1_qa_health_by_release"
V_ALI = "v"

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _guid():
    return uuid.uuid4().hex[:20]


def _src(alias):
    return {"SourceRef": {"Source": alias}}


def _col(alias, col):
    return {"Column": {"Expression": _src(alias), "Property": col}}


def _meas(alias, meas):
    return {"Measure": {"Expression": _src(alias), "Property": meas}}


def _from(alias, entity):
    return {"Name": alias, "Entity": entity, "Type": 0}


def _select_col(alias, entity, col):
    return {**_col(alias, col), "Name": f"{entity}.{col}"}


def _select_meas(alias, entity, meas):
    return {**_meas(alias, meas), "Name": f"{entity}.{meas}"}


def proto_query(frm: list, select: list):
    return {"Version": 2, "From": frm, "Select": select}


# ---------------------------------------------------------------------------
# Visual container builders
# ---------------------------------------------------------------------------

def _container(vid, x, y, z, w, h, config_obj, filters="[]", query_obj=None):
    c = {
        "id": vid,
        "x": x, "y": y, "z": z,
        "width": w, "height": h,
        "config": json.dumps(config_obj, separators=(",", ":")),
        "filters": filters,
    }
    if query_obj:
        c["query"] = json.dumps(query_obj, separators=(",", ":"))
    return c


def _cfg(visual_type, pq, projections, objects=None, vc_objects=None, tab=1000):
    name = _guid()
    cfg = {
        "name": name,
        "layouts": [{"id": 0, "position": {"x": 0, "y": 0, "z": 0,
                                            "width": 0, "height": 0, "tabOrder": tab}}],
        "singleVisual": {
            "visualType": visual_type,
            "projections": projections,
            "prototypeQuery": pq,
            "vcObjects": vc_objects or {},
        }
    }
    if objects:
        cfg["singleVisual"]["objects"] = objects
    return cfg


# ---- Text Box ---------------------------------------------------------------
def textbox(vid, x, y, w, h, text, font_size=18, bold=True, z=0):
    paragraphs = [{
        "name": _guid(),
        "textRuns": [{
            "name": _guid(),
            "value": text,
            "textStyle": {"fontWeight": "bold" if bold else "normal",
                          "fontSize": f"{font_size}pt"}
        }],
        "horizontalTextAlignment": "Center"
    }]
    cfg = {
        "name": _guid(),
        "layouts": [{"id": 0, "position": {"x": 0, "y": 0, "z": 0,
                                            "width": 0, "height": 0, "tabOrder": 0}}],
        "singleVisual": {
            "visualType": "textbox",
            "vcObjects": {
                "general": [{"properties": {"paragraphs": {"expr": {"Literal": {"Value": json.dumps(paragraphs)}}}}}]
            },
            "objects": {
                "general": [{"properties": {"paragraphs": {"expr": {"Literal": {"Value": json.dumps(paragraphs)}}}}}]
            },
            "paragraphs": paragraphs,
        }
    }
    return _container(vid, x, y, z, w, h, cfg)


# ---- Slicer -----------------------------------------------------------------
def slicer_col(vid, x, y, w, h, entity, alias, col, display_name, mode="Dropdown", z=0):
    pq = proto_query(
        [_from(alias, entity)],
        [_select_col(alias, entity, col)]
    )
    proj = {"Values": [{"queryRef": f"{entity}.{col}", "active": True}]}
    objects = {
        "data": [{"properties": {"mode": {"expr": {"Literal": {"Value": f"'{mode}'"}}}}}],
        "header": [{"properties": {
            "show": {"expr": {"Literal": {"Value": "true"}}},
            "fontColor": {"solid": {"color": "#252423"}},
            "text": {"expr": {"Literal": {"Value": f"'{display_name}'"}}}
        }}]
    }
    cfg = _cfg("slicer", pq, proj, objects=objects)
    return _container(vid, x, y, z, w, h, cfg)


def slicer_date(vid, x, y, w, h, z=0):
    entity, alias, col = "dim_date", "d", "full_date"
    pq = proto_query(
        [_from(alias, entity)],
        [_select_col(alias, entity, col)]
    )
    proj = {"Values": [{"queryRef": f"{entity}.{col}", "active": True}]}
    objects = {
        "data": [{"properties": {"mode": {"expr": {"Literal": {"Value": "'Between'"}}}}}],
        "header": [{"properties": {
            "show": {"expr": {"Literal": {"Value": "true"}}},
            "text": {"expr": {"Literal": {"Value": "'Date Range'"}}}
        }}]
    }
    cfg = _cfg("slicer", pq, proj, objects=objects)
    return _container(vid, x, y, z, w, h, cfg)


# ---- KPI Card ---------------------------------------------------------------
def card(vid, x, y, w, h, entity, alias, measure_name, title=None, font_size=24, z=0):
    pq = proto_query(
        [_from(alias, entity)],
        [_select_meas(alias, entity, measure_name)]
    )
    proj = {"Values": [{"queryRef": f"{entity}.{measure_name}", "active": True}]}
    title_val = title or measure_name
    vc_objects = {
        "title": [{"properties": {
            "show": {"expr": {"Literal": {"Value": "true"}}},
            "text": {"expr": {"Literal": {"Value": f"'{title_val}'"}}},
            "fontSize": {"expr": {"Literal": {"Value": "10"}}},
            "fontColor": {"solid": {"color": "#605E5C"}}
        }}],
        "labels": [{"properties": {
            "fontSize": {"expr": {"Literal": {"Value": str(font_size)}}},
            "color": {"solid": {"color": "#252423"}}
        }}]
    }
    cfg = _cfg("card", pq, proj, vc_objects=vc_objects)
    return _container(vid, x, y, z, w, h, cfg)


# ---- ETMI Hero Gauge --------------------------------------------------------
def etmi_gauge(vid, x, y, w, h, z=0):
    pq = proto_query(
        [_from(V_ALI, VIEW), _from("t", VIEW)],
        [
            {**_meas(V_ALI, "ETMI Score"),  "Name": f"{VIEW}.ETMI Score"},
            {**_meas("t",   "ETMI Target"), "Name": f"{VIEW}.ETMI Target"},
        ]
    )
    proj = {
        "Y":        [{"queryRef": f"{VIEW}.ETMI Score",  "active": True}],
        "MaxValue": [{"queryRef": f"{VIEW}.ETMI Target", "active": True}],
    }
    vc_objects = {
        "title": [{"properties": {
            "show": {"expr": {"Literal": {"Value": "true"}}},
            "text": {"expr": {"Literal": {"Value": "'ETMI Score (0\u2013100)'"}}},
            "fontSize": {"expr": {"Literal": {"Value": "11"}}},
            "fontColor": {"solid": {"color": "#252423"}}
        }}],
        "calloutValue": [{"properties": {
            "show": {"expr": {"Literal": {"Value": "true"}}},
            "fontSize": {"expr": {"Literal": {"Value": "22"}}}
        }}],
        "gauge": [{"properties": {
            "arcColor":    {"solid": {"color": "#0078D4"}},
            "targetColor": {"solid": {"color": "#A4262C"}}
        }}]
    }
    cfg = _cfg("gauge", pq, proj, vc_objects=vc_objects)
    return _container(vid, x, y, z, w, h, cfg)


# ---- ETMI Band Card ---------------------------------------------------------
def etmi_band_card(vid, x, y, w, h, z=0):
    pq = proto_query(
        [_from(V_ALI, VIEW)],
        [{**_meas(V_ALI, "ETMI Band"), "Name": f"{VIEW}.ETMI Band"}]
    )
    proj = {"Values": [{"queryRef": f"{VIEW}.ETMI Band", "active": True}]}
    vc_objects = {
        "title": [{"properties": {
            "show": {"expr": {"Literal": {"Value": "true"}}},
            "text": {"expr": {"Literal": {"Value": "'Maturity Band'"}}},
            "fontSize": {"expr": {"Literal": {"Value": "10"}}},
            "fontColor": {"solid": {"color": "#605E5C"}}
        }}],
        "labels": [{"properties": {
            "fontSize": {"expr": {"Literal": {"Value": "20"}}},
            "color":    {"solid": {"color": "#107C10"}}
        }}]
    }
    cfg = _cfg("card", pq, proj, vc_objects=vc_objects)
    return _container(vid, x, y, z, w, h, cfg)


# ---- ETMI Status Card -------------------------------------------------------
def etmi_status_card(vid, x, y, w, h, z=0):
    pq = proto_query(
        [_from(V_ALI, VIEW)],
        [{**_meas(V_ALI, "ETMI Status"), "Name": f"{VIEW}.ETMI Status"}]
    )
    proj = {"Values": [{"queryRef": f"{VIEW}.ETMI Status", "active": True}]}
    vc_objects = {
        "title": [{"properties": {
            "show": {"expr": {"Literal": {"Value": "true"}}},
            "text": {"expr": {"Literal": {"Value": "'ETMI Status'"}}},
            "fontSize": {"expr": {"Literal": {"Value": "10"}}},
            "fontColor": {"solid": {"color": "#605E5C"}}
        }}],
        "labels": [{"properties": {
            "fontSize": {"expr": {"Literal": {"Value": "18"}}},
            "color":    {"solid": {"color": "#252423"}}
        }}]
    }
    cfg = _cfg("card", pq, proj, vc_objects=vc_objects)
    return _container(vid, x, y, z, w, h, cfg)


# ---- ETMI Trend Line Chart --------------------------------------------------
def etmi_trend_line(vid, x, y, w, h, z=0):
    pq = proto_query(
        [_from("r", "dim_release"), _from(V_ALI, VIEW)],
        [
            {**_col("r",    "release_name"),  "Name": "dim_release.release_name"},
            {**_meas(V_ALI, "ETMI Score"),    "Name": f"{VIEW}.ETMI Score"},
            {**_meas(V_ALI, "ETMI Target"),   "Name": f"{VIEW}.ETMI Target"},
        ]
    )
    proj = {
        "Category": [{"queryRef": "dim_release.release_name",  "active": True}],
        "Y":        [{"queryRef": f"{VIEW}.ETMI Score",         "active": True}],
        "Y2":       [{"queryRef": f"{VIEW}.ETMI Target",        "active": True}],
    }
    vc_objects = {
        "title": [{"properties": {
            "show": {"expr": {"Literal": {"Value": "true"}}},
            "text": {"expr": {"Literal": {"Value": "'ETMI Score by Release'"}}}
        }}],
        "xAxis": [{"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}}}],
        "yAxis": [{"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}}}],
    }
    cfg = _cfg("lineChart", pq, proj, vc_objects=vc_objects)
    return _container(vid, x, y, z, w, h, cfg)


# ---- CXO Summary Table ------------------------------------------------------
def cxo_summary_table(vid, x, y, w, h, z=0):
    pq = proto_query(
        [_from("r", "dim_release"), _from(V_ALI, VIEW)],
        [
            {**_col("r",    "release_name"),            "Name": "dim_release.release_name"},
            {**_meas(V_ALI, "Automation Coverage %"),   "Name": f"{VIEW}.Automation Coverage %"},
            {**_meas(V_ALI, "Regression Automation %"), "Name": f"{VIEW}.Regression Automation %"},
            {**_meas(V_ALI, "Execution Efficiency %"),  "Name": f"{VIEW}.Execution Efficiency %"},
            {**_meas(V_ALI, "ETMI Score"),              "Name": f"{VIEW}.ETMI Score"},
            {**_meas(V_ALI, "ETMI Band"),               "Name": f"{VIEW}.ETMI Band"},
            {**_meas(V_ALI, "P1 Total Runs"),           "Name": f"{VIEW}.P1 Total Runs"},
            {**_meas(V_ALI, "P1 Pass Rate %"),          "Name": f"{VIEW}.P1 Pass Rate %"},
        ]
    )
    proj = {
        "Values": [
            {"queryRef": "dim_release.release_name",              "active": True},
            {"queryRef": f"{VIEW}.Automation Coverage %",         "active": True},
            {"queryRef": f"{VIEW}.Regression Automation %",       "active": True},
            {"queryRef": f"{VIEW}.Execution Efficiency %",        "active": True},
            {"queryRef": f"{VIEW}.ETMI Score",                    "active": True},
            {"queryRef": f"{VIEW}.ETMI Band",                     "active": True},
            {"queryRef": f"{VIEW}.P1 Total Runs",                 "active": True},
            {"queryRef": f"{VIEW}.P1 Pass Rate %",                "active": True},
        ]
    }
    vc_objects = {
        "title": [{"properties": {
            "show": {"expr": {"Literal": {"Value": "true"}}},
            "text": {"expr": {"Literal": {"Value": "'Release ETMI Breakdown'"}}}
        }}],
        "columnHeaders": [{"properties": {
            "fontColor": {"solid": {"color": "#252423"}},
            "backColor": {"solid": {"color": "#F3F2F1"}}
        }}],
    }
    cfg = _cfg("tableEx", pq, proj, vc_objects=vc_objects)
    return _container(vid, x, y, z, w, h, cfg)


# ---------------------------------------------------------------------------
# Assemble P1 | CXO Quality Dashboard page
# ---------------------------------------------------------------------------

def build_p1_page():
    W, H = 1280, 720
    containers = []
    vid = 1

    # ── Row 0: Title bar (full width, h=44) ──────────────────────────────────
    containers.append(textbox(vid, 0, 0, W, 44, "P1 | CXO Quality Dashboard", font_size=20, bold=True))
    vid += 1

    # ── Row 1: Slicers (y=52, h=60) ──────────────────────────────────────────
    containers.append(slicer_col(vid,   0, 52, 300, 60, "dim_release", "r", "release_name", "Release"))
    vid += 1
    containers.append(slicer_col(vid, 312, 52, 300, 60, "dim_squad",   "s", "squad_name",   "Squad"))
    vid += 1
    containers.append(slicer_date(vid, 624, 52, 646, 60))
    vid += 1

    # ── Row 2: ETMI gauge + 3 component cards + band + status (y=124, h=158) ─
    # gauge(280) | 8 | AutoCov(196) | 8 | RegAuto(196) | 8 | ExecEff(196) | 8 | band(180) | 8 | status(200) = 1280
    row2_y, row2_h = 124, 158
    containers.append(etmi_gauge(vid, 0, row2_y, 280, row2_h))
    vid += 1

    comp_w, gap = 196, 8
    comp_x = 280 + gap
    for measure, title in [
        ("Automation Coverage %",   "Automation Coverage %"),
        ("Regression Automation %", "Regression Automation %"),
        ("Execution Efficiency %",  "Execution Efficiency %"),
    ]:
        containers.append(card(vid, comp_x, row2_y, comp_w, row2_h, VIEW, V_ALI, measure, title, font_size=28))
        vid += 1
        comp_x += comp_w + gap

    band_w = 180
    containers.append(etmi_band_card(vid, comp_x, row2_y, band_w, row2_h))
    vid += 1
    comp_x += band_w + gap

    status_w = W - comp_x
    containers.append(etmi_status_card(vid, comp_x, row2_y, status_w, row2_h))
    vid += 1

    # ── Row 3: ETMI trend line (y=294, h=194) ────────────────────────────────
    row3_y, row3_h = 294, 194
    containers.append(etmi_trend_line(vid, 0, row3_y, W, row3_h))
    vid += 1

    # ── Row 4: CXO summary table (y=496, h=224) ──────────────────────────────
    containers.append(cxo_summary_table(vid, 0, 496, W, 224))
    vid += 1

    section = {
        "id": 0,
        "name": _guid(),
        "displayName": "P1 | CXO Quality Dashboard",
        "filters": "[]",
        "ordinal": 0,
        "visualContainers": containers,
        "config": "{}",
        "displayOption": 1,
        "width": W,
        "height": H,
    }
    return section


# ---------------------------------------------------------------------------
# Read / write PBIX
# ---------------------------------------------------------------------------

def read_layout(pbix_path):
    with zipfile.ZipFile(pbix_path, "r") as z:
        with z.open("Report/Layout") as f:
            raw = f.read().decode("utf-16-le")
    return json.loads(raw)


def write_pbix(pbix_in, pbix_out, new_layout):
    layout_bytes = json.dumps(new_layout, separators=(",", ":"), ensure_ascii=False).encode("utf-16-le")

    tmp = pbix_out + ".tmp"
    # Read from pbix_in, write to tmp, then atomically replace pbix_out.
    # This works whether pbix_in == pbix_out or not, without a redundant copy.
    with zipfile.ZipFile(pbix_in, "r") as zin, \
         zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename == "Report/Layout":
                zout.writestr(item, layout_bytes)
            else:
                zout.writestr(item, zin.read(item.filename))
    os.replace(tmp, pbix_out)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"Reading layout from: {PBIX_IN}")
    layout = read_layout(PBIX_IN)

    print("Building P1 | CXO Quality Dashboard \u2026")
    p1_section = build_p1_page()

    layout["sections"] = [p1_section]

    print(f"Writing to: {PBIX_OUT}")
    write_pbix(PBIX_IN, PBIX_OUT, layout)
    print("Done. Open TMR_p1_dashboard.pbix in Power BI Desktop, then refresh data.")
