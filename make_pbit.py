#!/usr/bin/env python3
"""
Create QA-Pipeline-Report.pbit (Power BI Template) from:
  - Existing PBIX (for Report layout, Settings, StaticResources, etc.)
  - pbixproj.bim  (TMSL model with all 19 tables + 13 relationships)

A .pbit file is identical to .pbix except:
  - Contains  DataModelSchema  (JSON, UTF-16 LE) instead of  DataModel  (binary)
  - Opening it in PBI Desktop triggers credential prompt + refresh

Run: python make_pbit.py
"""
import json
import zipfile
import io
import shutil
from pathlib import Path

PBIX_IN  = Path(r"c:\TM_PBI\qa_pipeline\QA-Pipeline-Report.pbix")
BIM_FILE = Path(r"c:\TM_PBI\qa_pipeline\pbixproj.bim")
PBIT_OUT = Path(r"c:\TM_PBI\qa_pipeline\QA-Pipeline-Report.pbit")

# Files to copy byte-for-byte from source PBIX (these are binary/UTF-16 blobs)
COPY_ENTRIES = {
    "Version",
    "DiagramLayout",
    "Report/Layout",
    "Settings",
    "Metadata",
    "SecurityBindings",
    "Report/StaticResources/SharedResources/BaseThemes/CY26SU02.json",
}

# ── Build DataModelSchema ─────────────────────────────────────────────────────
def build_data_model_schema(bim: dict) -> bytes:
    """
    BIM JSON encoded as UTF-16 LE WITHOUT BOM — same encoding PBI uses for
    DiagramLayout, Version, and other text blobs inside the ZIP.
    """
    schema = {
        "name": bim["name"],
        "compatibilityLevel": bim["compatibilityLevel"],
        "model": bim["model"],
    }
    json_str = json.dumps(schema, ensure_ascii=False, indent=None, separators=(",", ":"))
    return json_str.encode("utf-16-le")   # NO BOM — matches DiagramLayout/Version encoding

# ── Build updated [Content_Types].xml ────────────────────────────────────────
def build_content_types(src_zip: zipfile.ZipFile) -> bytes:
    """
    Copy original [Content_Types].xml (UTF-8 with BOM) from the source PBIX,
    swap  DataModel  for  DataModelSchema  in the Override entries.
    """
    raw = src_zip.read("[Content_Types].xml")
    UTF8_BOM = b"\xef\xbb\xbf"
    if raw.startswith(UTF8_BOM):
        text = raw[3:].decode("utf-8")
    else:
        text = raw.decode("utf-8")
    text = text.replace(
        'PartName="/DataModel" ContentType=""',
        'PartName="/DataModelSchema" ContentType=""',
    )
    return UTF8_BOM + text.encode("utf-8")

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("Reading BIM model ...")
    bim = json.loads(BIM_FILE.read_text(encoding="utf-8"))
    tables = bim["model"]["tables"]
    rels   = bim["model"].get("relationships", [])
    print(f"  Tables: {len(tables)}, Relationships: {len(rels)}")
    for t in tables:
        print(f"    - {t['name']}")

    schema_bytes = build_data_model_schema(bim)

    print(f"\nBuilding PBIT from: {PBIX_IN.name}")

    with zipfile.ZipFile(PBIX_IN, "r") as src_zip:
        ct_bytes = build_content_types(src_zip)   # derived from original

        with zipfile.ZipFile(PBIT_OUT, "w", compression=zipfile.ZIP_DEFLATED) as dst_zip:

            # Write updated content types (UTF-8 with BOM, DataModel→DataModelSchema)
            dst_zip.writestr("[Content_Types].xml", ct_bytes)

            # Copy whitelisted entries
            for entry in src_zip.namelist():
                if entry == "[Content_Types].xml":
                    continue                          # already written above
                if entry == "DataModel":
                    continue                          # drop binary model
                if entry in COPY_ENTRIES:
                    dst_zip.writestr(entry, src_zip.read(entry))

            # Write DataModelSchema (JSON model definition)
            dst_zip.writestr("DataModelSchema", schema_bytes)

    size_kb = PBIT_OUT.stat().st_size / 1024
    print(f"\nCreated: {PBIT_OUT}  ({size_kb:.1f} KB)")
    print("\nContents:")
    with zipfile.ZipFile(PBIT_OUT, "r") as z:
        for n in z.namelist():
            print(f"  {n}")
    print("\nDone. Open QA-Pipeline-Report.pbit in Power BI Desktop,")
    print("enter DB credentials when prompted, then save as .pbix.")

if __name__ == "__main__":
    main()
