"""
build_p1_layout.py
Generates P1 dashboard layout JSON and injects it into the PBIX file.
Canvas: 1280 x 720
"""
import json
import shutil
import sys
import zipfile
import os
import uuid
from pathlib import Path

PBIX_IN  = r"C:\TM_PBI\TMR_backup_pre_p1.pbix"
PBIX_OUT = r"C:\TM_PBI\TMR_p1_dashboard.pbix"

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

def _container(vid, x, y, z, w, h, config_obj, tab=0, filters="[]", query_obj=None):
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
def card(vid, x, y, w, h, entity, alias, measure_name, title=None, z=0):
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
            "fontSize": {"expr": {"Literal": {"Value": "24"}}},
            "color": {"solid": {"color": "#252423"}}
        }}]
    }
    cfg = _cfg("card", pq, proj, vc_objects=vc_objects)
    return _container(vid, x, y, z, w, h, cfg)


# ---- Gauge ------------------------------------------------------------------
def gauge(vid, x, y, w, h, z=0):
    alias_f, alias_t = "f", "ft"
    pq = proto_query(
        [_from(alias_f, "fact_test_run"), _from(alias_t, "fact_test_run")],
        [
            {**_meas(alias_f, "Pass Rate %"), "Name": "fact_test_run.Pass Rate %"},
            {**_meas(alias_t, "P1 Target Pass Rate %"), "Name": "fact_test_run.P1 Target Pass Rate %"},
        ]
    )
    proj = {
        "Y": [{"queryRef": "fact_test_run.Pass Rate %", "active": True}],
        "MaxValue": [{"queryRef": "fact_test_run.P1 Target Pass Rate %", "active": True}],
    }
    vc_objects = {
        "title": [{"properties": {
            "show": {"expr": {"Literal": {"Value": "true"}}},
            "text": {"expr": {"Literal": {"Value": "'Pass Rate vs Target'"}}}
        }}],
        "calloutValue": [{"properties": {
            "show": {"expr": {"Literal": {"Value": "true"}}}
        }}]
    }
    cfg = _cfg("gauge", pq, proj, vc_objects=vc_objects)
    return _container(vid, x, y, z, w, h, cfg)


# ---- Stacked Bar ------------------------------------------------------------
def stacked_bar(vid, x, y, w, h, z=0):
    pq = proto_query(
        [_from("r", "dim_release"), _from("f", "fact_test_run")],
        [
            {**_col("r", "release_name"), "Name": "dim_release.release_name"},
            {**_col("f", "run_status"), "Name": "fact_test_run.run_status"},
            {**_meas("f", "Total Runs"), "Name": "fact_test_run.Total Runs"},
        ]
    )
    proj = {
        "Category": [{"queryRef": "dim_release.release_name", "active": True}],
        "Series": [{"queryRef": "fact_test_run.run_status", "active": True}],
        "Y": [{"queryRef": "fact_test_run.Total Runs", "active": True}],
    }
    vc_objects = {
        "title": [{"properties": {
            "show": {"expr": {"Literal": {"Value": "true"}}},
            "text": {"expr": {"Literal": {"Value": "'Runs by Release & Status'"}}}
        }}],
        "xAxis": [{"properties": {
            "show": {"expr": {"Literal": {"Value": "true"}}}
        }}],
        "yAxis": [{"properties": {
            "show": {"expr": {"Literal": {"Value": "true"}}}
        }}],
    }
    cfg = _cfg("barChart", pq, proj, vc_objects=vc_objects)
    return _container(vid, x, y, z, w, h, cfg)


# ---- Line Chart -------------------------------------------------------------
def line_chart(vid, x, y, w, h, z=0):
    pq = proto_query(
        [_from("d", "dim_date"), _from("f", "fact_test_run")],
        [
            {**_col("d", "full_date"), "Name": "dim_date.full_date"},
            {**_meas("f", "Pass Rate %"), "Name": "fact_test_run.Pass Rate %"},
        ]
    )
    proj = {
        "Category": [{"queryRef": "dim_date.full_date", "active": True}],
        "Y": [{"queryRef": "fact_test_run.Pass Rate %", "active": True}],
    }
    vc_objects = {
        "title": [{"properties": {
            "show": {"expr": {"Literal": {"Value": "true"}}},
            "text": {"expr": {"Literal": {"Value": "'Pass Rate % Trend'"}}}
        }}],
        "xAxis": [{"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}}},],
        "yAxis": [{"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}}},],
    }
    cfg = _cfg("lineChart", pq, proj, vc_objects=vc_objects)
    return _container(vid, x, y, z, w, h, cfg)


# ---- Summary Table ----------------------------------------------------------
def summary_table(vid, x, y, w, h, z=0):
    pq = proto_query(
        [_from("r", "dim_release"), _from("f", "fact_test_run"), _from("d", "dim_defect")],
        [
            {**_col("r", "release_name"), "Name": "dim_release.release_name"},
            {**_meas("f", "Total Runs"), "Name": "fact_test_run.Total Runs"},
            {**_meas("f", "Passed Runs"), "Name": "fact_test_run.Passed Runs"},
            {**_meas("f", "Failed Runs"), "Name": "fact_test_run.Failed Runs"},
            {**_meas("f", "Pass Rate (formatted)"), "Name": "fact_test_run.Pass Rate (formatted)"},
            {**_meas("d", "Open Defects"), "Name": "dim_defect.Open Defects"},
            {**_meas("d", "Critical Defects"), "Name": "dim_defect.Critical Defects"},
        ]
    )
    proj = {
        "Values": [
            {"queryRef": "dim_release.release_name", "active": True},
            {"queryRef": "fact_test_run.Total Runs", "active": True},
            {"queryRef": "fact_test_run.Passed Runs", "active": True},
            {"queryRef": "fact_test_run.Failed Runs", "active": True},
            {"queryRef": "fact_test_run.Pass Rate (formatted)", "active": True},
            {"queryRef": "dim_defect.Open Defects", "active": True},
            {"queryRef": "dim_defect.Critical Defects", "active": True},
        ]
    }
    vc_objects = {
        "title": [{"properties": {
            "show": {"expr": {"Literal": {"Value": "true"}}},
            "text": {"expr": {"Literal": {"Value": "'Release Summary'"}}}
        }}],
        "columnHeaders": [{"properties": {
            "fontColor": {"solid": {"color": "#252423"}},
            "backColor": {"solid": {"color": "#F3F2F1"}}
        }}],
    }
    cfg = _cfg("tableEx", pq, proj, vc_objects=vc_objects)
    return _container(vid, x, y, z, w, h, cfg)


# ---- MoM Status Card --------------------------------------------------------
def status_card(vid, x, y, w, h, z=0):
    pq = proto_query(
        [_from("f", "fact_test_run")],
        [{**_meas("f", "P1 Pass Rate Status"), "Name": "fact_test_run.P1 Pass Rate Status"}]
    )
    proj = {"Values": [{"queryRef": "fact_test_run.P1 Pass Rate Status", "active": True}]}
    vc_objects = {
        "title": [{"properties": {
            "show": {"expr": {"Literal": {"Value": "true"}}},
            "text": {"expr": {"Literal": {"Value": "'P1 Status'"}}},
            "fontSize": {"expr": {"Literal": {"Value": "10"}}}
        }}],
        "labels": [{"properties": {
            "fontSize": {"expr": {"Literal": {"Value": "18"}}}
        }}]
    }
    cfg = _cfg("card", pq, proj, vc_objects=vc_objects)
    return _container(vid, x, y, z, w, h, cfg)


# ---------------------------------------------------------------------------
# Assemble P1 page
# ---------------------------------------------------------------------------

def build_p1_page():
    W, H = 1280, 720
    containers = []
    vid = 1

    # Row 0: Title bar (full width)
    containers.append(textbox(vid, 0, 0, W, 44, "P1 – Test Run Summary", font_size=20, bold=True))
    vid += 1

    # Row 1: Slicers (y=52)
    containers.append(slicer_col(vid, 0,   52, 300, 64, "dim_release", "r", "release_name", "Release"))
    vid += 1
    containers.append(slicer_col(vid, 312, 52, 300, 64, "dim_squad",   "s", "squad_name",   "Squad"))
    vid += 1
    containers.append(slicer_date(vid, 624, 52, 646, 64))
    vid += 1

    # Row 2: KPI cards + status + gauge (y=128, h=110)
    # Layout: 4 cards×196 (188+8gap) = 784 + status 200 + 8gap + gauge 288 = 1280
    card_w, card_h, gap = 188, 110, 8
    card_y = 128
    cards = [
        ("fact_test_run", "f", "Total Runs",            "Total Runs"),
        ("fact_test_run", "f", "Pass Rate (formatted)",  "Pass Rate"),
        ("dim_defect",    "d", "Open Defects",           "Open Defects"),
        ("dim_defect",    "d", "Critical Defects",       "Critical"),
    ]
    for i, (entity, alias, meas, title) in enumerate(cards):
        containers.append(card(vid, i * (card_w + gap), card_y, card_w, card_h, entity, alias, meas, title))
        vid += 1
    # P1 Status card
    status_x = len(cards) * (card_w + gap)
    status_w = 200
    containers.append(status_card(vid, status_x, card_y, status_w, card_h))
    vid += 1
    # Gauge — remaining width (1280 - 784 - 200 - 8 = 288)
    gauge_x = status_x + status_w + gap
    gauge_w = W - gauge_x
    containers.append(gauge(vid, gauge_x, card_y, gauge_w, card_h))
    vid += 1

    # Row 3: Bar + Line (y=252, h=210)
    chart_y = 252
    chart_h = 210
    containers.append(stacked_bar(vid, 0,   chart_y, 620, chart_h))
    vid += 1
    containers.append(line_chart(vid,  630, chart_y, 640, chart_h))
    vid += 1

    # Row 4: Table (y=474, h=238)
    containers.append(summary_table(vid, 0, 474, W, 238))
    vid += 1

    section = {
        "id": 0,
        "name": _guid(),
        "displayName": "P1 - Test Run Summary",
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

    shutil.copy2(pbix_in, pbix_out)
    tmp = pbix_out + ".tmp"
    with zipfile.ZipFile(pbix_out, "r") as zin, \
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

    print("Building P1 page …")
    p1_section = build_p1_page()

    # Replace sections with P1 page only
    layout["sections"] = [p1_section]

    print(f"Writing to: {PBIX_OUT}")
    write_pbix(PBIX_IN, PBIX_OUT, layout)
    print("Done. Open TMR_p1_dashboard.pbix in Power BI Desktop, then refresh data.")
