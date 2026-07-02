#!/usr/bin/env python3
"""Index GraphPad Prism PZFX project tables and graph-to-table hints.

This is an intake helper, not a statistical detector and not a provenance
verifier. It records parseable table/graph metadata from supplied PZFX files so
authors can prepare source exports and manifests more easily.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any
import xml.etree.ElementTree as ET


PZFX_EXTS = {".pzfx"}
GRAPH_NODE_NAMES = {"graph", "graphsheet", "graphpage"}
TABLE_NODE_NAMES = {"table"}
SOURCE_HINT_NAMES = {
    "datatable",
    "sourcetable",
    "source",
    "tableid",
    "table",
    "sheet",
    "datasheet",
}


def xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def xml_node_text(node: ET.Element) -> str:
    return " ".join(text.strip() for text in node.itertext() if text and text.strip())


def first_child_text(node: ET.Element, names: set[str]) -> str:
    for child in list(node):
        if xml_local_name(child.tag) in names:
            text = xml_node_text(child)
            if text:
                return text
    return ""


def safe_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def normalized_id(value: str | None) -> str:
    return safe_key(value or "").lower()


def collect_pzfx_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in PZFX_EXTS)


def table_title(table: ET.Element, index: int) -> str:
    title = first_child_text(table, {"title", "name"})
    if title:
        return safe_key(title)
    for attr in ("Title", "title", "Name", "name", "ID", "id"):
        value = table.attrib.get(attr)
        if value and value.strip():
            return safe_key(value)
    return f"Table {index}"


def table_identifier(table: ET.Element, index: int) -> str:
    for attr in ("ID", "id", "Guid", "GUID", "Name", "name", "Title", "title"):
        value = table.attrib.get(attr)
        if value and value.strip():
            return safe_key(value)
    return f"table_{index}"


def column_nodes(table: ET.Element) -> list[ET.Element]:
    return [
        child
        for child in list(table)
        if xml_local_name(child.tag).endswith("column") or xml_local_name(child.tag) == "column"
    ]


def column_title(column: ET.Element, index: int) -> str:
    for attr in ("Title", "title", "Name", "name"):
        value = column.attrib.get(attr)
        if value and value.strip():
            return safe_key(value)
    title = first_child_text(column, {"title", "name"})
    return safe_key(title) if title else f"column_{index}"


def column_value_count(column: ET.Element) -> int:
    values = [
        xml_node_text(node)
        for node in column.iter()
        if xml_local_name(node.tag) in {"d", "data", "value"} and xml_node_text(node)
    ]
    if values:
        return len(values)
    direct_values = []
    for child in list(column):
        name = xml_local_name(child.tag)
        if name in {"title", "name", "subcolumn"}:
            continue
        text = xml_node_text(child)
        if text:
            direct_values.append(text)
    return len(direct_values)


def graph_title(graph: ET.Element, index: int) -> str:
    title = first_child_text(graph, {"title", "name"})
    if title:
        return safe_key(title)
    for attr in ("Title", "title", "Name", "name", "ID", "id"):
        value = graph.attrib.get(attr)
        if value and value.strip():
            return safe_key(value)
    return f"Graph {index}"


def graph_identifier(graph: ET.Element, index: int) -> str:
    for attr in ("ID", "id", "Guid", "GUID", "Name", "name", "Title", "title"):
        value = graph.attrib.get(attr)
        if value and value.strip():
            return safe_key(value)
    return f"graph_{index}"


def graph_source_hints(graph: ET.Element, table_lookup: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    hints: dict[str, dict[str, str]] = {}

    def add(raw_value: str, evidence: str) -> None:
        value = safe_key(raw_value)
        if not value:
            return
        normalized = normalized_id(value)
        table = table_lookup.get(normalized)
        if table:
            key = str(table["table_id"])
            if key in hints:
                current = hints[key].get("match_basis", "")
                if evidence not in current.split("; "):
                    hints[key]["match_basis"] = f"{current}; {evidence}" if current else evidence
            else:
                hints[key] = {
                    "table_id": str(table["table_id"]),
                    "table_title": str(table["title"]),
                    "match_basis": evidence,
                }
            return
        if len(value) >= 2:
            key = value
            if key in hints:
                current = hints[key].get("match_basis", "")
                if evidence not in current.split("; "):
                    hints[key]["match_basis"] = f"{current}; {evidence}" if current else evidence
            else:
                hints[key] = {
                    "table_id": value,
                    "table_title": "",
                    "match_basis": evidence,
                }

    for attr, value in graph.attrib.items():
        attr_name = attr.lower()
        if value and any(token in attr_name for token in ("table", "source", "sheet", "data")):
            add(value, f"graph attribute `{attr}`")

    for node in graph.iter():
        name = xml_local_name(node.tag)
        text = first_child_text(node, {"title", "name"}) or xml_node_text(node)
        if name in SOURCE_HINT_NAMES and text:
            add(text, f"graph child `{name}`")
        for attr, value in node.attrib.items():
            attr_name = attr.lower()
            if value and any(token in attr_name for token in ("table", "source", "sheet", "data")):
                add(value, f"graph descendant `{name}` attribute `{attr}`")

    return sorted(hints.values(), key=lambda item: (item.get("table_title", ""), item.get("table_id", "")))


def parse_pzfx(root: Path, path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    rel = str(path.relative_to(root))
    try:
        document = ET.parse(path).getroot()
    except Exception as exc:  # noqa: BLE001
        error = {
            "path": rel,
            "stage": "prism_project_intake",
            "error": f"PZFX XML parse failed: {exc}",
        }
        return {
            "path": rel,
            "parse_status": "error",
            "table_count": 0,
            "graph_count": 0,
            "errors": [error],
        }, [], [], [], [error]

    tables: list[dict[str, Any]] = []
    table_lookup: dict[str, dict[str, Any]] = {}
    for index, table in enumerate([node for node in document.iter() if xml_local_name(node.tag) == "table"], start=1):
        columns = column_nodes(table)
        value_counts = [column_value_count(column) for column in columns]
        record = {
            "source_pzfx": rel,
            "table_id": table_identifier(table, index),
            "title": table_title(table, index),
            "column_count": len(columns),
            "row_count_estimate": max(value_counts) if value_counts else 0,
            "columns": [column_title(column, col_index) for col_index, column in enumerate(columns, start=1)][:40],
            "interpretation": "Prism table metadata for intake review; export CSV/XLSX source data before relying on statistical coverage.",
        }
        tables.append(record)
        for value in (record["table_id"], record["title"]):
            key = normalized_id(str(value))
            if key:
                table_lookup[key] = record

    graphs: list[dict[str, Any]] = []
    graph_links: list[dict[str, Any]] = []
    for index, graph in enumerate([node for node in document.iter() if xml_local_name(node.tag) in GRAPH_NODE_NAMES], start=1):
        graph_id = graph_identifier(graph, index)
        title = graph_title(graph, index)
        hints = graph_source_hints(graph, table_lookup)
        graph_record = {
            "source_pzfx": rel,
            "graph_id": graph_id,
            "title": title,
            "possible_source_tables": hints,
            "interpretation": "possible Prism graph-to-table linkage for manifest preparation; not verified provenance evidence",
        }
        graphs.append(graph_record)
        for hint in hints:
            graph_links.append({
                "source_pzfx": rel,
                "graph_id": graph_id,
                "graph_title": title,
                "table_id": hint.get("table_id", ""),
                "table_title": hint.get("table_title", ""),
                "match_basis": hint.get("match_basis", ""),
                "interpretation": "possible Prism graph-to-table linkage; not verified provenance and requires exported graph/table/source records for verification",
            })

    status = "parsed" if tables or graphs else "parsed_no_tables_or_graphs"
    return {
        "path": rel,
        "parse_status": status,
        "table_count": len(tables),
        "graph_count": len(graphs),
        "possible_graph_table_link_count": len(graph_links),
        "errors": [],
    }, tables, graphs, graph_links, []


def scan(root: Path) -> dict[str, Any]:
    pzfx_files: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    graphs: list[dict[str, Any]] = []
    graph_table_links: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for path in collect_pzfx_files(root):
        file_payload, file_tables, file_graphs, file_links, file_errors = parse_pzfx(root, path)
        pzfx_files.append(file_payload)
        tables.extend(file_tables)
        graphs.extend(file_graphs)
        graph_table_links.extend(file_links)
        errors.extend(file_errors)

    return {
        "schema_version": "0.1.0",
        "extractor": "scripts.prism_project_intake",
        "scope_note": (
            "Best-effort GraphPad Prism PZFX project intake. Table and graph metadata are "
            "manifest-preparation hints only; possible graph-to-table links are not verified "
            "figure provenance and do not replace CSV/XLSX exports, Prism graph exports, raw "
            "records, or analysis code."
        ),
        "input": {
            "package": str(root),
            "pzfx_files": len(pzfx_files),
        },
        "pzfx_files": pzfx_files,
        "tables": tables,
        "graphs": graphs,
        "graph_table_links": graph_table_links,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--output", type=Path, default=Path("prism_project_intake.json"))
    args = parser.parse_args()

    root = args.package_dir.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Package directory not found: {root}")
    output = args.output.expanduser().resolve()
    payload = scan(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "pzfx_files": payload["input"]["pzfx_files"],
        "tables": len(payload["tables"]),
        "graphs": len(payload["graphs"]),
        "possible_graph_table_links": len(payload["graph_table_links"]),
        "errors": len(payload["errors"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
