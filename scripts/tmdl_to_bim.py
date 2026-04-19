#!/usr/bin/env python3
"""
scripts/tmdl_to_bim.py — Regenerate pbixproj.bim from TMDL table definitions.

Reads every *.tmdl in powerbi/semantic-model/definition/tables/ and converts
it to the BIM JSON format that make_pbit.py uses to build the PBIT file.
Also reads relationships.tmdl and converts them to BIM relationship entries.

Run from the repo root:
    python scripts/tmdl_to_bim.py
"""
from __future__ import annotations
import json
import re
import uuid
from pathlib import Path

TMDL_TABLES_DIR = Path("powerbi/semantic-model/definition/tables")
TMDL_REL_FILE   = Path("powerbi/semantic-model/definition/relationships.tmdl")
BIM_OUT         = Path("pbixproj.bim")

# Data type map: TMDL → BIM
DTYPE_MAP = {
    "string":   "string",
    "int64":    "int64",
    "double":   "double",
    "decimal":  "decimal",
    "dateTime": "dateTime",
    "boolean":  "boolean",
}


def _uid() -> str:
    return str(uuid.uuid4())


def parse_tmdl_table(path: Path) -> dict:
    """Parse a single TMDL file and return a BIM table dict."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    table_name = ""
    lineage_tag = ""
    columns: list[dict] = []
    measures: list[dict] = []
    partition_source = ""

    # Extract table name + lineageTag (first two lines)
    m = re.match(r"^table (.+)$", lines[0].strip())
    if m:
        table_name = m.group(1).strip()
    m2 = re.search(r"lineageTag: ([0-9a-f\-]+)", lines[1] if len(lines) > 1 else "")
    if m2:
        lineage_tag = m2.group(1)

    # Parse sections line by line
    i = 2
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # ── measure block ──────────────────────────────────────────────────────
        if stripped.startswith("measure "):
            # measure 'Name' = EXPR  (may continue on next lines with indentation)
            m_match = re.match(r"measure '(.+?)'\s*=\s*(.*)", stripped)
            if m_match:
                measure_name = m_match.group(1)
                expr_lines = [m_match.group(2)]
                i += 1
                # Collect continuation lines (indented further)
                while i < len(lines):
                    next_stripped = lines[i].strip()
                    if next_stripped.startswith("lineageTag:"):
                        m_lt = re.search(r"lineageTag: ([0-9a-f\-]+)", next_stripped)
                        m_lt_val = m_lt.group(1) if m_lt else _uid()
                        i += 1
                        continue
                    if next_stripped.startswith("formatString:"):
                        fmt = next_stripped.split(":", 1)[1].strip()
                        measures.append({
                            "name": measure_name,
                            "expression": "\n".join(expr_lines).strip(),
                            "formatString": fmt,
                            "lineageTag": m_lt_val if 'm_lt_val' in dir() else _uid(),
                        })
                        i += 1
                        break
                    if next_stripped.startswith("annotation "):
                        i += 1
                        continue
                    # Check if this line starts a new top-level block
                    indent = len(lines[i]) - len(lines[i].lstrip())
                    if indent <= 1 and next_stripped and not next_stripped.startswith("//"):
                        # Back one, close measure without formatString
                        measures.append({
                            "name": measure_name,
                            "expression": "\n".join(expr_lines).strip(),
                            "lineageTag": m_lt_val if 'm_lt_val' in dir() else _uid(),
                        })
                        break
                    expr_lines.append(lines[i].strip())
                    i += 1
                else:
                    if not any(m["name"] == measure_name for m in measures):
                        measures.append({
                            "name": measure_name,
                            "expression": "\n".join(expr_lines).strip(),
                            "lineageTag": _uid(),
                        })
                continue

        # ── column block ───────────────────────────────────────────────────────
        if stripped.startswith("column "):
            col_name = re.match(r"column (.+)$", stripped).group(1).strip()
            col: dict = {"name": col_name, "lineageTag": _uid()}
            i += 1
            while i < len(lines):
                inner = lines[i].strip()
                if inner.startswith("dataType:"):
                    dt = inner.split(":", 1)[1].strip()
                    col["dataType"] = DTYPE_MAP.get(dt, dt)
                elif inner.startswith("lineageTag:"):
                    col["lineageTag"] = inner.split(":", 1)[1].strip()
                elif inner.startswith("sourceColumn:"):
                    col["sourceColumn"] = inner.split(":", 1)[1].strip()
                elif inner == "isHidden":
                    col["isHidden"] = True
                elif inner.startswith("formatString:"):
                    col["formatString"] = inner.split(":", 1)[1].strip()
                elif inner.startswith("column ") or inner.startswith("measure ") or \
                     inner.startswith("partition ") or inner.startswith("annotation ") or \
                     (inner and not inner.startswith("//") and
                      len(lines[i]) - len(lines[i].lstrip()) <= 1):
                    break
                i += 1
            columns.append(col)
            continue

        # ── partition / M source ───────────────────────────────────────────────
        if stripped.startswith("partition "):
            # Collect M source expression
            src_lines: list[str] = []
            i += 1
            in_source = False
            while i < len(lines):
                inner = lines[i].strip()
                if inner.startswith("source ="):
                    in_source = True
                    after = inner[len("source ="):].strip()
                    if after:
                        src_lines.append(after)
                elif in_source:
                    src_lines.append(lines[i].rstrip())
                elif inner.startswith("mode:"):
                    pass  # skip
                i += 1
            partition_source = "\n".join(src_lines).strip()
            continue

        i += 1

    # Build BIM table object
    table: dict = {
        "name": table_name,
        "lineageTag": lineage_tag or _uid(),
    }
    if measures:
        table["measures"] = measures
    if columns:
        table["columns"] = columns
    if partition_source:
        table["partitions"] = [
            {
                "name": table_name,
                "mode": "import",
                "source": {
                    "type": "m",
                    "expression": partition_source,
                },
            }
        ]
    return table


def parse_relationships(path: Path) -> list[dict]:
    """Parse relationships.tmdl → list of BIM relationship dicts."""
    text = path.read_text(encoding="utf-8")
    rels: list[dict] = []
    current: dict | None = None

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("relationship "):
            if current:
                rels.append(current)
            current = {"name": stripped.split(" ", 1)[1].strip()}
        elif stripped.startswith("fromColumn:") and current is not None:
            parts = stripped.split(":", 1)[1].strip().split(".")
            current["fromTable"] = parts[0]
            current["fromColumn"] = parts[1] if len(parts) > 1 else parts[0]
        elif stripped.startswith("toColumn:") and current is not None:
            parts = stripped.split(":", 1)[1].strip().split(".")
            current["toTable"] = parts[0]
            current["toColumn"] = parts[1] if len(parts) > 1 else parts[0]
        elif stripped == "isActive: false" and current is not None:
            current["isActive"] = False

    if current:
        rels.append(current)

    return rels


def main():
    print("Reading TMDL tables ...")
    tmdl_files = sorted(TMDL_TABLES_DIR.glob("*.tmdl"))
    tables: list[dict] = []
    for f in tmdl_files:
        t = parse_tmdl_table(f)
        tables.append(t)
        col_count = len(t.get("columns", []))
        meas_count = len(t.get("measures", []))
        print(f"  {t['name']:40s} cols={col_count:3d} measures={meas_count:2d}")

    print(f"\nParsed {len(tables)} tables.")

    print("\nReading relationships ...")
    rels = parse_relationships(TMDL_REL_FILE)
    print(f"  {len(rels)} relationships found.")

    # Load existing BIM to preserve header metadata
    existing = json.loads(BIM_OUT.read_text(encoding="utf-8"))

    bim = {
        "name": existing["name"],
        "compatibilityLevel": existing["compatibilityLevel"],
        "model": {
            **{k: v for k, v in existing["model"].items()
               if k not in ("tables", "relationships")},
            "tables": tables,
            "relationships": rels,
        },
    }

    BIM_OUT.write_text(
        json.dumps(bim, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nWrote {BIM_OUT}  ({BIM_OUT.stat().st_size // 1024} KB)")
    print("Done — run  python make_pbit.py  to produce QA-Pipeline-Report.pbit")


if __name__ == "__main__":
    main()
