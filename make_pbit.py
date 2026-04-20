#!/usr/bin/env python3
"""
make_pbit.py
Builds QA-Pipeline-Report.pbit from:
  - QA-Pipeline-Report.pbix  (for Report layout, Settings, theme, Metadata, etc.)
  - pbixproj.bim             (TMSL semantic model with all tables + relationships)

A .pbit file is identical to .pbix except:
  - Contains DataModelSchema (JSON, UTF-16 LE) instead of DataModel (binary)
  - Opening it in PBI Desktop triggers credential prompt + refresh

Run: python make_pbit.py
"""
import json
import re
import zipfile
from pathlib import Path

PBIX_CANDIDATES = [
    Path(r"c:\TM_PBI\qa_pipeline\QA-Pipeline-Report.pbix"),
    Path(r"c:\TM_PBI\qa_pipeline\TMR.pbix"),
]
BIM_FILE = Path(r"c:\TM_PBI\qa_pipeline\pbixproj.bim")
PBIT_OUT = Path(r"c:\TM_PBI\qa_pipeline\QA-Pipeline-Report.pbit")

REQUIRED_PBIX_ENTRIES = {
    "Version",
    "[Content_Types].xml",
    "DataModel",
    "Report/Layout",
}

REQUIRED_CXO_TABLES = {
    "dim_application",
    "dim_environment",
    "dim_status",
    "dim_root_cause",
    "dim_tester",
    "fact_defect_link",
    "fact_cycle_snapshot",
    "vw_p2_defect_density",
    "vw_p7_environment_health",
    "vw_p8_release_snapshot",
    "vw_qm_quality_effectiveness",
}

REQUIRED_CXO_MEASURES = {
    "vw_p1_qa_health_by_release": {
        "Automation Coverage %",
        "Regression Automation %",
        "Execution Efficiency %",
        "ETMI Score",
        "ETMI Band",
        "ETMI Target",
        "ETMI Status",
    },
    "vw_p7_environment_health": {
        "P7 Total Runs",
        "P7 Failed Runs",
        "P7 Blocked Runs",
        "P7 Pass Rate %",
    },
    "vw_p8_release_snapshot": {
        "P8 Pass Rate %",
        "P8 Coverage Rate %",
        "P8 Automation Rate %",
        "P8 Open Critical Defects",
    },
    "vw_qm_quality_effectiveness": {
        "QM Defect Leakage Rate %",
        "QM Defect Removal Efficiency %",
        "QM Requirements Without Tests %",
        "QM Avg Resolution Hours",
    },
}


def normalize_expressions(obj):
    """Recursively convert array-form M expressions to single strings (TMDL → TMSL)."""
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key == "expression" and isinstance(val, list):
                obj[key] = "\n".join(val)
            else:
                normalize_expressions(val)
    elif isinstance(obj, list):
        for item in obj:
            normalize_expressions(item)


def sanitize_partition_self_references(model: dict):
    """Rename M step names that collide with table names to avoid cyclic query references."""
    for table in model.get("tables", []):
        table_name = table.get("name")
        if not table_name:
            continue

        step_decl_pattern = re.compile(
            rf"(?m)^(\s*){re.escape(table_name)}\s*=\s*Source\{{\[Schema=",
        )
        in_pattern = re.compile(
            rf"(?m)^\s*in\s+{re.escape(table_name)}\s*$",
        )

        for partition in table.get("partitions", []):
            source = partition.get("source") or {}
            expr = source.get("expression")
            if not expr:
                continue

            expr_text = "\n".join(expr) if isinstance(expr, list) else str(expr)
            if not step_decl_pattern.search(expr_text):
                continue
            if not in_pattern.search(expr_text):
                continue

            expr_text = step_decl_pattern.sub(r"\1Result = Source{[Schema=", expr_text, count=1)
            expr_text = in_pattern.sub("in\n    Result", expr_text, count=1)
            source["expression"] = expr_text


def build_data_model_schema(bim: dict) -> bytes:
    import copy
    schema = {
        "name": bim["name"],
        "compatibilityLevel": bim["compatibilityLevel"],
        "model": copy.deepcopy(bim["model"]),
    }
    normalize_expressions(schema["model"])
    sanitize_partition_self_references(schema["model"])
    json_str = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
    return json_str.encode("utf-16-le")  # no BOM — matches PBI internal encoding


def choose_pbix_source() -> Path:
    """Choose the first healthy PBIX candidate containing a non-trivial DataModel."""
    for candidate in PBIX_CANDIDATES:
        if not candidate.exists():
            continue
        try:
            with zipfile.ZipFile(candidate, "r") as z:
                names = set(z.namelist())
                if not REQUIRED_PBIX_ENTRIES.issubset(names):
                    continue
                data_model = z.getinfo("DataModel")
                # Tiny DataModel is a strong sign of a broken or empty source shell.
                if data_model.file_size < 50_000:
                    continue
            return candidate
        except Exception:
            continue
    raise FileNotFoundError(
        "No healthy PBIX source found. Checked: "
        + ", ".join(str(p) for p in PBIX_CANDIDATES)
    )


def build_content_types(src_zip: zipfile.ZipFile) -> bytes:
    """Preserve source XML formatting and only replace /DataModel with /DataModelSchema."""
    raw = src_zip.read("[Content_Types].xml")
    utf8_bom = b"\xef\xbb\xbf"
    text = raw[3:].decode("utf-8") if raw.startswith(utf8_bom) else raw.decode("utf-8")

    updated, count = re.subn(
        r'PartName="/DataModel"',
        'PartName="/DataModelSchema"',
        text,
        count=1,
    )

    if count == 0:
        insert = '<Override PartName="/DataModelSchema" ContentType="" />'
        if "</Types>" in text:
            updated = text.replace("</Types>", f"{insert}</Types>", 1)
        else:
            updated = text

    return utf8_bom + updated.encode("utf-8")


def validate_cxo_coverage(bim: dict):
    """Fail fast if CXO table/view or metric coverage is incomplete."""
    tables = {t.get("name"): t for t in bim.get("model", {}).get("tables", [])}

    missing_tables = sorted(name for name in REQUIRED_CXO_TABLES if name not in tables)
    if missing_tables:
        raise ValueError(
            "Missing required CXO tables/views in BIM: " + ", ".join(missing_tables)
        )

    missing_measures = []
    for table_name, required in REQUIRED_CXO_MEASURES.items():
        table = tables.get(table_name)
        if table is None:
            missing_measures.append(f"{table_name}: <table missing>")
            continue

        present = {m.get("name") for m in table.get("measures", []) if m.get("name")}
        absent = sorted(name for name in required if name not in present)
        if absent:
            missing_measures.append(f"{table_name}: {', '.join(absent)}")

    if missing_measures:
        raise ValueError(
            "Missing required CXO measures in BIM: " + " | ".join(missing_measures)
        )


def main():
    pbix_in = choose_pbix_source()

    print(f"Reading BIM: {BIM_FILE}")
    bim = json.loads(BIM_FILE.read_text(encoding="utf-8"))
    validate_cxo_coverage(bim)
    tables = bim["model"]["tables"]
    rels   = bim["model"].get("relationships", [])
    measures_total = sum(len(t.get("measures", [])) for t in tables)
    print(f"  Tables: {len(tables)}, Relationships: {len(rels)}, Measures: {measures_total}")

    schema_bytes = build_data_model_schema(bim)

    print(f"\nBuilding PBIT from: {pbix_in.name}")
    with zipfile.ZipFile(pbix_in, "r") as src_zip:
        ct_bytes = build_content_types(src_zip)

        with zipfile.ZipFile(PBIT_OUT, "w", compression=zipfile.ZIP_DEFLATED) as dst_zip:
            # Preserve PBIX entry order exactly: Version must be first
            for entry in src_zip.namelist():
                if entry == "DataModel":
                    dst_zip.writestr("DataModelSchema", schema_bytes)
                elif entry == "[Content_Types].xml":
                    dst_zip.writestr("[Content_Types].xml", ct_bytes)
                else:
                    dst_zip.writestr(entry, src_zip.read(entry))

    size_kb = round(PBIT_OUT.stat().st_size / 1024, 1)
    print(f"\nCreated: {PBIT_OUT} ({size_kb} KB)")

    print("\nContents:")
    with zipfile.ZipFile(PBIT_OUT, "r") as z:
        for n in z.namelist():
            info = z.getinfo(n)
            print(f"  {n}  ({info.file_size} bytes)")

    print("\nTables in model:")
    for t in tables:
        m_count = len(t.get("measures", []))
        marker = f"  [{m_count} measures]" if m_count else ""
        print(f"  {t['name']}{marker}")

    print("\nNext steps:")
    print("  1. Double-click QA-Pipeline-Report.pbit to open in Power BI Desktop")
    print("  2. Enter SQL Server credentials: 127.0.0.1,1433 / Reporting_DB")
    print("  3. Wait for data refresh")
    print("  4. Build your canvas using Fields pane")
    print("  5. File > Save As > QA-Pipeline-Report.pbix")


if __name__ == "__main__":
    main()
