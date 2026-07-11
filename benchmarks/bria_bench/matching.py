"""Exact, auditable matching of BRIA-Bench labels to observations."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
import unicodedata
from typing import Any, Mapping, Sequence


_RISK_RE = re.compile(r"^R([0-4])$")
_FIGURE_RE = re.compile(
    r"(?<![a-z0-9])(?:(supplemental|supplementary|supp\.?|s)\s*)?"
    r"(?:figure|fig\.?)\s*[_ .-]*(\d+)\s*([a-z])?",
    re.IGNORECASE,
)
_SHORT_SUPP_FIGURE_RE = re.compile(r"(?<![a-z0-9])s(\d+)([a-z])?\b", re.IGNORECASE)
_PANEL_RE = re.compile(r"\bpanel\s*[_ .-]*(\d+)?\s*([a-z])\b", re.IGNORECASE)
_PAGE_RE = re.compile(r"\bpages?\s*[_ .-]*(\d+)\b", re.IGNORECASE)
_TABLE_RE = re.compile(r"\btables?\s*[_ .-]*([0-9]+[a-z]?)\b", re.IGNORECASE)
_SHEET_RE = re.compile(r"\bsheets?\s*[_ .-]*(\d+)\b", re.IGNORECASE)
_COLUMN_RE = re.compile(r"\bcolumns?\s*[:#]?\s*([a-z]{1,3}(?:\s*(?:,|and|to|-)\s*[a-z]{1,3})*)\b", re.IGNORECASE)
_ROW_RE = re.compile(r"\brows?\s*[:#]?\s*([0-9]+(?:\s*(?:,|and|to|-)\s*[0-9]+)*)\b", re.IGNORECASE)
_PARAGRAPH_RE = re.compile(r"\bparagraphs?\s*[_ .-]*(\d+)\b", re.IGNORECASE)
_SECTION_RE = re.compile(r"\b(?:section\s*[:#-]?\s*)?(introduction|background|methods?|materials?|results?|discussion|conclusion|abstract|supplement(?:ary)?)\s+section\b|\bsection\s*[:#-]?\s*(introduction|background|methods?|materials?|results?|discussion|conclusion|abstract|supplement(?:ary)?)\b", re.IGNORECASE)
_TIME_DAY_RE = re.compile(r"(?<![a-z0-9])(?:day\s*(\d+)|(\d+)\s*days?|d\s*(\d+))\b", re.IGNORECASE)
_CELL_RE = re.compile(r"(?<![a-z0-9])([a-z]{1,3})(\d+)(?::([a-z]{1,3})(\d+))?\b", re.IGNORECASE)
_FILE_RE = re.compile(r"(?<![a-z0-9])(?:[~./\\_-]*[a-z0-9][a-z0-9._/\\_-]*)\.(?:pdf|png|jpe?g|tiff?|xlsx?|csv|docx?)\b", re.IGNORECASE)
_FILE_SUFFIX_RE = re.compile(r"\.(?:pdf|png|jpe?g|tiff?|xlsx?|csv|docx?)$", re.IGNORECASE)
_CELL_TEXT_RE = re.compile(r"\b(?:cells?|cell\s+range|range)\s*[:#-]?\s*([a-z]{1,3}\d+(?::[a-z]{1,3}\d+)?)\b", re.IGNORECASE)
_NAMED_SHEET_RE = re.compile(r"\bsheet\s+([a-z][a-z0-9 _-]*?)(?=\s*(?:,|;|\bcell|\brange|$))", re.IGNORECASE)
_FIGURE_CHAIN_RE = re.compile(r"(?:\band\s+|[_/,;&]+)\d+\s*[a-z]\b", re.IGNORECASE)
_GENERIC_LOCATION_TOKENS = frozenset({
    "cell",
    "cells",
    "column",
    "columns",
    "day",
    "days",
    "fig",
    "figure",
    "file",
    "page",
    "pages",
    "panel",
    "paragraph",
    "paragraphs",
    "range",
    "region",
    "row",
    "rows",
    "section",
    "sections",
    "sheet",
    "sheets",
    "table",
    "tables",
    "timepoint",
    "timepoints",
})
_IGNORABLE_REMAINDER_TOKENS = _GENERIC_LOCATION_TOKENS | frozenset({
    "a",
    "an",
    "and",
    "at",
    "by",
    "file",
    "find",
    "from",
    "in",
    "located",
    "of",
    "on",
    "or",
    "refer",
    "review",
    "see",
    "source",
    "the",
    "to",
    "with",
})


@dataclass(frozen=True)
class Compatibility:
    """The independent compatibility dimensions and audit evidence for an edge."""

    compatible: bool
    issue_compatible: bool
    location_compatible: bool
    risk_compatible: bool
    score: tuple[int, ...]
    reasons: tuple[str, ...] = ()
    components: Mapping[str, Any] = field(default_factory=dict)

    @property
    def auditable_components(self) -> Mapping[str, Any]:
        return self.components

    def to_dict(self) -> dict[str, Any]:
        return {
            "compatible": self.compatible,
            "issue_compatible": self.issue_compatible,
            "location_compatible": self.location_compatible,
            "risk_compatible": self.risk_compatible,
            "score": list(self.score),
            "reasons": list(self.reasons),
            "components": _json_value(dict(self.components)),
        }


@dataclass(frozen=True)
class Match:
    label_id: str
    observation_id: str
    compatibility: Compatibility

    @property
    def score(self) -> tuple[int, ...]:
        return self.compatibility.score

    @property
    def reasons(self) -> tuple[str, ...]:
        return self.compatibility.reasons

    @property
    def components(self) -> Mapping[str, Any]:
        return self.compatibility.components

    def to_dict(self) -> dict[str, Any]:
        return {
            "label_id": self.label_id,
            "observation_id": self.observation_id,
            "compatibility": self.compatibility.to_dict(),
            "score": list(self.score),
            "reasons": list(self.reasons),
            "components": _json_value(dict(self.components)),
        }


@dataclass(frozen=True)
class MatchResult:
    matches: tuple[Match, ...]
    unmatched_label_ids: tuple[str, ...]
    unmatched_observation_ids: tuple[str, ...]
    candidate_edges: tuple[Match, ...]
    assignment_ambiguous: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "matches": [item.to_dict() for item in self.matches],
            "unmatched_label_ids": list(self.unmatched_label_ids),
            "unmatched_observation_ids": list(self.unmatched_observation_ids),
            "candidate_edges": [item.to_dict() for item in self.candidate_edges],
            "assignment_ambiguous": self.assignment_ambiguous,
        }

    as_dict = to_dict


@dataclass(frozen=True)
class _Figure:
    supplement: bool
    number: int
    panel: str | None = None


@dataclass
class _Location:
    files: set[str] = field(default_factory=set)
    pages: set[int] = field(default_factory=set)
    figures: set[_Figure] = field(default_factory=set)
    panels: set[str] = field(default_factory=set)
    tables: set[str] = field(default_factory=set)
    sheets: set[tuple[str, Any]] = field(default_factory=set)
    columns: set[str] = field(default_factory=set)
    rows: set[int] = field(default_factory=set)
    sections: set[str] = field(default_factory=set)
    paragraphs: set[int] = field(default_factory=set)
    timepoints: set[int] = field(default_factory=set)
    terms: set[str] = field(default_factory=set)
    cell_ranges: set[tuple[str, int, str, int]] = field(default_factory=set)
    regions: list[tuple[float, float, float, float, str]] = field(default_factory=list)


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_value(item) for item in value]
    return value


def _norm(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("location values must be strings")
    return unicodedata.normalize("NFKC", value).casefold().replace("\\", "/").strip()


def _risk(value: object, *, label: bool = False) -> tuple[int, int] | int:
    if label:
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueError("risk_range must contain two risk levels")
        levels = tuple(_risk(item) for item in value)
        assert isinstance(levels[0], int) and isinstance(levels[1], int)
        if levels[0] > levels[1]:
            raise ValueError("risk_range must be ordered")
        return levels[0], levels[1]
    if not isinstance(value, str):
        raise ValueError("risk level must be R0 through R4")
    match = _RISK_RE.fullmatch(value.strip().upper())
    if match is None:
        raise ValueError("risk level must be R0 through R4")
    return int(match.group(1))


def _field(item: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in item:
            return item[name]
    return None


def _expand_numbers(value: object) -> set[int]:
    text = str(value).strip()
    result: set[int] = set()
    pieces = re.split(r"\s*(?:,|and|to|-)\s*", text, flags=re.IGNORECASE)
    for piece in pieces:
        if not piece:
            continue
        if not piece.isdigit() or int(piece) < 1:
            raise ValueError("row values must be positive integers")
        result.add(int(piece))
    if len(pieces) >= 2 and ("-" in text or re.search(r"\bto\b", text, re.IGNORECASE)):
        bounds = [int(piece) for piece in pieces if piece.isdigit()]
        if len(bounds) == 2:
            if bounds[0] > bounds[1] or bounds[1] - bounds[0] > 10000:
                raise ValueError("invalid row range")
            result.update(range(bounds[0], bounds[1] + 1))
    return result


def _columns(value: object) -> set[str]:
    if isinstance(value, (list, tuple, set, frozenset)):
        values = value
    else:
        values = re.findall(r"(?<![a-z])([a-z]{1,3})(?![a-z])", str(value), re.IGNORECASE)
    result: set[str] = set()
    for item in values:
        text = str(item).strip().upper()
        if not re.fullmatch(r"[A-Z]{1,3}", text):
            raise ValueError("invalid column")
        result.add(text)
    return result


def _column_number(value: str) -> int:
    number = 0
    for char in value:
        number = number * 26 + ord(char) - ord("A") + 1
    return number


def _column_name(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def _cell_range(location: _Location, value: object) -> None:
    text = str(value).strip().upper()
    match = _CELL_RE.fullmatch(text)
    if match is None:
        raise ValueError("invalid cell_range")
    first_col, first_row, last_col, last_row = match.groups()
    last_col = last_col or first_col
    last_row = last_row or first_row
    start_col, end_col = _column_number(first_col), _column_number(last_col)
    start_row, end_row = int(first_row), int(last_row)
    if start_row < 1 or start_col > end_col or start_row > end_row or end_col - start_col > 10000 or end_row - start_row > 10000:
        raise ValueError("invalid cell_range bounds")
    location.cell_ranges.add((first_col, start_row, last_col, end_row))
    location.columns.update(_column_name(item) for item in range(start_col, end_col + 1))
    location.rows.update(range(start_row, end_row + 1))


def _add_figures(location: _Location, text: str) -> None:
    figure_matches = list(_FIGURE_RE.finditer(text))
    for match in figure_matches:
        supplement = bool(match.group(1))
        number = int(match.group(2))
        if number < 1:
            raise ValueError("figure numbers must be positive")
        panel = match.group(3).upper() if match.group(3) else None
        location.figures.add(_Figure(supplement, number, panel))
        if panel:
            location.panels.add(panel)
        tail = text[match.end() : match.end() + 32]
        for chained in re.finditer(r"(?:[_/,;&]+|\band\s+)(\d+)\s*([a-z])\b", tail, re.IGNORECASE):
            chained_number = int(chained.group(1))
            if chained_number < 1:
                raise ValueError("figure numbers must be positive")
            chained_panel = chained.group(2).upper()
            location.figures.add(_Figure(supplement, chained_number, chained_panel))
            location.panels.add(chained_panel)
    for match in _SHORT_SUPP_FIGURE_RE.finditer(text):
        if int(match.group(1)) < 1:
            raise ValueError("figure numbers must be positive")
        panel = match.group(2).upper() if match.group(2) else None
        location.figures.add(_Figure(True, int(match.group(1)), panel))
        if panel:
            location.panels.add(panel)
    for match in _PANEL_RE.finditer(text):
        panel = match.group(2).upper()
        location.panels.add(panel)
        if match.group(1):
            if int(match.group(1)) < 1:
                raise ValueError("figure numbers must be positive")
            location.figures.add(_Figure(False, int(match.group(1)), panel))


def _add_structured_figure(location: _Location, value: object) -> None:
    text = _norm(value)
    before = len(location.figures)
    _add_figures(location, text)
    if len(location.figures) == before:
        match = re.fullmatch(r"(?:s\s*)?(\d+)\s*([a-z])?", text, re.IGNORECASE)
        if match is None or int(match.group(1)) < 1:
            raise ValueError("invalid figure")
        location.figures.add(_Figure(text.startswith("s"), int(match.group(1)), match.group(2).upper() if match.group(2) else None))
        if match.group(2):
            location.panels.add(match.group(2).upper())


def _structured_snapshot(location: _Location) -> tuple[Any, ...]:
    return (
        frozenset(location.files),
        frozenset(location.pages),
        frozenset(location.figures),
        frozenset(location.panels),
        frozenset(location.tables),
        frozenset(location.sheets),
        frozenset(location.columns),
        frozenset(location.rows),
        frozenset(location.sections),
        frozenset(location.paragraphs),
        frozenset(location.timepoints),
        frozenset(location.cell_ranges),
        tuple(location.regions),
    )


def _has_structured_location(location: _Location) -> bool:
    return any(
        (
            location.files,
            location.pages,
            location.figures,
            location.panels,
            location.tables,
            location.sheets,
            location.columns,
            location.rows,
            location.sections,
            location.paragraphs,
            location.timepoints,
            location.cell_ranges,
            location.regions,
        )
    )


def _is_generic_location_text(text: str) -> bool:
    tokens = re.findall(r"[a-z]+", unicodedata.normalize("NFKC", text).casefold())
    return not tokens or all(token in _GENERIC_LOCATION_TOKENS or token in _IGNORABLE_REMAINDER_TOKENS for token in tokens)


def _filename_span(text: str) -> str | None:
    candidate = text.strip()
    if len(candidate) >= 2 and candidate[0] == candidate[-1] and candidate[0] in {'"', "'"}:
        candidate = candidate[1:-1].strip()
        return candidate if candidate and _FILE_SUFFIX_RE.search(candidate) else None
    if not _FILE_SUFFIX_RE.search(candidate):
        return None
    first_word = re.match(r"[a-z]+\b", candidate, re.IGNORECASE)
    if first_word and first_word.group(0).casefold() in _IGNORABLE_REMAINDER_TOKENS:
        return None
    return candidate


def _opaque_remainder(text: str) -> str:
    if _filename_span(text) is not None:
        return ""
    remainder = text
    for pattern in (
        _FIGURE_RE,
        _SHORT_SUPP_FIGURE_RE,
        _PANEL_RE,
        _PAGE_RE,
        _TABLE_RE,
        _SHEET_RE,
        _NAMED_SHEET_RE,
        _COLUMN_RE,
        _ROW_RE,
        _PARAGRAPH_RE,
        _CELL_TEXT_RE,
        _FILE_RE,
        _SECTION_RE,
        _TIME_DAY_RE,
        _FIGURE_CHAIN_RE,
    ):
        remainder = pattern.sub(" ", remainder)
    remainder = re.sub(r"\b(?:and|or|with|at|by|from|in|of|on|refer|review|see|source|the|to)\b", " ", remainder)
    remainder = re.sub(r"[^\w\s_-]+", " ", remainder, flags=re.IGNORECASE)
    remainder = _norm(" ".join(remainder.split()))
    tokens = re.findall(r"[a-z]+", remainder)
    if not tokens or all(token in _IGNORABLE_REMAINDER_TOKENS for token in tokens):
        return ""
    return remainder


def _add_text(location: _Location, value: object, *, terms: bool = False) -> None:
    text = _norm(value)
    before = _structured_snapshot(location)
    _add_figures(location, text)
    for match in _PAGE_RE.finditer(text):
        if int(match.group(1)) < 1:
            raise ValueError("page numbers must be positive")
        location.pages.add(int(match.group(1)))
    for match in _TABLE_RE.finditer(text):
        if int(re.match(r"\d+", match.group(1)).group()) < 1:
            raise ValueError("table numbers must be positive")
        location.tables.add(match.group(1).casefold())
    for match in _SHEET_RE.finditer(text):
        if int(match.group(1)) < 1:
            raise ValueError("sheet numbers must be positive")
        location.sheets.add(("index", int(match.group(1))))
    for match in _NAMED_SHEET_RE.finditer(text):
        name = _norm(match.group(1))
        if name and not name.isdigit():
            location.sheets.add(("name", name))
    for match in _COLUMN_RE.finditer(text):
        location.columns.update(_columns(match.group(1)))
    for match in _ROW_RE.finditer(text):
        location.rows.update(_expand_numbers(match.group(1)))
    for match in _PARAGRAPH_RE.finditer(text):
        if int(match.group(1)) < 1:
            raise ValueError("paragraph numbers must be positive")
        location.paragraphs.add(int(match.group(1)))
    for match in _CELL_TEXT_RE.finditer(text):
        _cell_range(location, match.group(1))
    for match in _SECTION_RE.finditer(text):
        section = next(item for item in match.groups() if item is not None)
        section = _norm(section).removesuffix(" section").strip()
        if section:
            location.sections.add(section)
    if text in {"abstract", "introduction", "background", "methods", "materials", "results", "discussion", "conclusion", "supplement", "supplementary"}:
        location.sections.add(text)
    for match in _TIME_DAY_RE.finditer(text):
        location.timepoints.add(int(next(item for item in match.groups() if item is not None)))
    whole_filename = _filename_span(text)
    if whole_filename is not None:
        location.files.add(_norm(whole_filename))
    else:
        for match in _FILE_RE.finditer(text):
            location.files.add(_norm(match.group(0)))
    if terms:
        if before == _structured_snapshot(location) and not _is_generic_location_text(text) and text:
            location.terms.add(text)
    elif before == _structured_snapshot(location) and not _has_structured_location(location):
        if not _is_generic_location_text(text) and text:
            location.terms.add(text)
    elif before != _structured_snapshot(location):
        remainder = _opaque_remainder(text)
        if remainder:
            location.terms.add(remainder)


def _add_region(location: _Location, value: object) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("region must be an object")
    required = ("x", "y", "width", "height", "coordinate_space")
    if any(key not in value for key in required):
        raise ValueError("region is missing coordinates")
    try:
        numbers = tuple(float(value[key]) for key in required[:4])
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("region coordinates must be finite numbers") from exc
    if any(not math.isfinite(item) for item in numbers):
        raise ValueError("region coordinates must be finite numbers")
    x, y, width, height = numbers
    space = _norm(value["coordinate_space"])
    if space not in {"normalized_0_1", "pixels"}:
        raise ValueError("unsupported region coordinate space")
    if width <= 0 or height <= 0 or x < 0 or y < 0:
        raise ValueError("region coordinates are out of range")
    if space == "normalized_0_1" and (x + width > 1 or y + height > 1):
        raise ValueError("normalized region is out of range")
    location.regions.append((x, y, width, height, space))


def _parse_location(value: object) -> _Location:
    location = _Location()
    if isinstance(value, str):
        _add_text(location, value)
        return location
    if not isinstance(value, Mapping) or not value:
        raise ValueError("location must be a non-empty string or object")

    if "text" in value:
        _add_text(location, value["text"])
    if "terms" in value:
        terms = value["terms"]
        if not isinstance(terms, (list, tuple, set, frozenset)):
            raise ValueError("location terms must be a list")
        for term in terms:
            _add_text(location, term, terms=True)
    if "file" in value:
        file_value = _norm(value["file"])
        if not file_value:
            raise ValueError("file must not be empty")
        location.files.add(file_value)
    if "page" in value:
        if isinstance(value["page"], bool) or not isinstance(value["page"], int) or value["page"] < 1:
            raise ValueError("page must be a positive integer")
        location.pages.add(value["page"])
    if "figure" in value:
        figure_text = _norm(value["figure"])
        before = set(location.figures)
        _add_structured_figure(location, figure_text)
        if "panel" in value:
            panel_text = _norm(value["panel"])
            panel_match = re.fullmatch(r"(?:s?\s*)?(\d+)?\s*([a-z])", panel_text, re.IGNORECASE)
            if panel_match is None:
                raise ValueError("invalid panel")
            panel = panel_match.group(2).upper()
            location.panels.add(panel)
            number = panel_match.group(1)
            if number:
                if int(number) < 1:
                    raise ValueError("figure numbers must be positive")
                location.figures.add(_Figure(panel_text.startswith("s"), int(number), panel))
            elif before or location.figures:
                for figure in list(location.figures):
                    location.figures.discard(figure)
                    location.figures.add(_Figure(figure.supplement, figure.number, panel))
            else:
                raise ValueError("panel requires a figure or explicit figure number")
    elif "panel" in value:
        panel_text = _norm(value["panel"])
        panel_match = re.fullmatch(r"(?:s?\s*)?(\d+)?\s*([a-z])", panel_text, re.IGNORECASE)
        if panel_match is None:
            raise ValueError("invalid panel")
        location.panels.add(panel_match.group(2).upper())
        if panel_match.group(1):
            if int(panel_match.group(1)) < 1:
                raise ValueError("figure numbers must be positive")
            location.figures.add(_Figure(panel_text.startswith("s"), int(panel_match.group(1)), panel_match.group(2).upper()))
    if "table" in value:
        table = _norm(value["table"])
        table_match = re.fullmatch(r"(?:table\s*)?([0-9]+[a-z]?)", table, re.IGNORECASE)
        if table_match is None:
            raise ValueError("invalid table")
        if int(re.match(r"\d+", table_match.group(1)).group()) < 1:
            raise ValueError("table numbers must be positive")
        location.tables.add(table_match.group(1))
    if "sheet" in value:
        sheet = _norm(value["sheet"])
        sheet_match = re.fullmatch(r"sheet\s*(\d+)", sheet, re.IGNORECASE)
        if sheet_match:
            if int(sheet_match.group(1)) < 1:
                raise ValueError("sheet numbers must be positive")
            location.sheets.add(("index", int(sheet_match.group(1))))
        else:
            if not sheet:
                raise ValueError("sheet must not be empty")
            location.sheets.add(("name", sheet))
    if "columns" in value:
        location.columns.update(_columns(value["columns"]))
    if "rows" in value:
        rows = value["rows"] if isinstance(value["rows"], (list, tuple, set, frozenset)) else [value["rows"]]
        for row in rows:
            location.rows.update(_expand_numbers(row))
    if "cell_range" in value:
        _cell_range(location, value["cell_range"])
    if "section" in value:
        section = _norm(value["section"])
        if not section:
            raise ValueError("section must not be empty")
        location.sections.add(section)
    if "paragraph" in value:
        paragraph = value["paragraph"]
        if isinstance(paragraph, str):
            if re.fullmatch(r"[1-9][0-9]*", paragraph) is None:
                raise ValueError("paragraph must be a canonical positive integer")
            paragraph = int(paragraph)
        if isinstance(paragraph, bool) or not isinstance(paragraph, int) or paragraph < 1:
            raise ValueError("paragraph must be a positive integer")
        location.paragraphs.add(paragraph)
    if "region" in value or "regions" in value:
        regions = value.get("regions", value.get("region"))
        if isinstance(regions, (list, tuple)):
            for region in regions:
                _add_region(location, region)
        else:
            _add_region(location, regions)
    return location


def _has_figure_panel(location: _Location) -> bool:
    return any(figure.panel is not None for figure in location.figures)


def _figure_relation(expected: _Location, observed: _Location, components: dict[str, Any], reasons: list[str]) -> bool:
    if not expected.figures:
        return True
    if not observed.figures:
        reasons.append("observation lacks the expected figure")
        return False
    exact_panel = 0
    parent = 0
    satisfied = False
    for wanted in expected.figures:
        candidates = [item for item in observed.figures if item.supplement == wanted.supplement and item.number == wanted.number]
        if not candidates:
            reasons.append("observation lacks one expected figure or supplement")
            return False
        if wanted.panel is not None:
            if not any(item.panel == wanted.panel for item in candidates):
                reasons.append("observation lacks one expected figure panel")
                return False
            exact_panel += 1
            satisfied = True
        else:
            parent += int(any(item.panel is not None for item in candidates))
            satisfied = True
    if not satisfied:
        reasons.append("figure number, supplement, or panel differs")
        return False
    components["figure_panel_exact"] = bool(exact_panel)
    components["parent_figure"] = bool(parent)
    components["figure_panel_intersection"] = bool(exact_panel)
    if exact_panel:
        reasons.append("figure and panel tokens agree")
    elif parent:
        reasons.append("observed figure is a more specific child of the expected figure")
    return True


def _subset_relation(name: str, expected: set[Any], observed: set[Any], reasons: list[str], components: dict[str, Any]) -> bool:
    if not expected:
        return True
    if not observed or not expected.issubset(observed):
        if expected.isdisjoint(observed):
            reasons.append(f"{name} differs")
        else:
            reasons.append(f"observation is less specific for {name}")
        return False
    components[f"{name}_agree"] = True
    return True


def _region_relation(expected: _Location, observed: _Location, reasons: list[str], components: dict[str, Any]) -> bool:
    if not expected.regions:
        return True
    if not observed.regions:
        reasons.append("observation lacks the expected region")
        return False
    best_any: tuple[Any, ...] | None = None
    best: tuple[Any, ...] | None = None
    for left in expected.regions:
        for right in observed.regions:
            if left[4] != right[4]:
                continue
            ix = max(0.0, min(left[0] + left[2], right[0] + right[2]) - max(left[0], right[0]))
            iy = max(0.0, min(left[1] + left[3], right[1] + right[3]) - max(left[1], right[1]))
            intersection = ix * iy
            if intersection <= 0:
                continue
            left_area, right_area = left[2] * left[3], right[2] * right[3]
            iou = intersection / (left_area + right_area - intersection)
            smaller = intersection / min(left_area, right_area)
            candidate = (max(iou, smaller), iou, smaller, left[:4], right[:4])
            if best_any is None or candidate > best_any:
                best_any = candidate
            if iou >= 0.10 or smaller >= 0.50:
                if best is None or candidate > best:
                    best = candidate
    if best is None:
        if best_any is not None:
            components["region_iou"] = round(best_any[1], 6)
            components["region_intersection_over_smaller"] = round(best_any[2], 6)
        if any(left[4] == right[4] for left in expected.regions for right in observed.regions):
            reasons.append("same-space regions are disjoint or have insufficient overlap")
        else:
            reasons.append("regions have no comparable same-space pair")
        return False
    components["region_iou"] = round(best[1], 6)
    components["region_intersection_over_smaller"] = round(best[2], 6)
    components["region_overlap"] = round(best[0], 6)
    reasons.append(f"same-space regions overlap (IoU={best[1]:.3f}, smaller={best[2]:.3f})")
    return True


def _location_compare(expected: _Location, observed: _Location) -> tuple[bool, tuple[int, ...], list[str], dict[str, Any]]:
    reasons: list[str] = []
    components: dict[str, Any] = {}
    if not _figure_relation(expected, observed, components, reasons):
        return False, (0, 0, 0, 0, 0, 0, 0), reasons, components

    if expected.files:
        if not observed.files:
            reasons.append("observation lacks the expected file")
            return False, (0, 0, 0, 0, 0, 0, 0), reasons, components
        expected_paths = {_norm(item) for item in expected.files}
        observed_paths = {_norm(item) for item in observed.files}
        exact = bool(expected_paths & observed_paths)
        basename = bool({item.rsplit("/", 1)[-1] for item in expected_paths} & {item.rsplit("/", 1)[-1] for item in observed_paths})
        if not exact and not basename and not (components.get("figure_panel_intersection") and _has_figure_panel(expected) and _has_figure_panel(observed)):
            reasons.append("explicit file basenames differ")
            return False, (0, 0, 0, 0, 0, 0, 0), reasons, components
        if exact:
            components["file_exact"] = True
            components["file_panel_exact"] = bool(components.get("figure_panel_intersection"))
            reasons.append("file paths agree exactly")
        elif basename:
            components["file_basename"] = True
            reasons.append("file basenames agree")
        else:
            components["file_conflict_resolved_by_figure_panel"] = True
            reasons.append("file conflict is resolved by a concrete figure/panel intersection")
    elif expected.files and not observed.files:
        return False, (0, 0, 0, 0, 0, 0, 0), reasons, components

    expected_figure_panels = {item.panel for item in expected.figures if item.panel is not None}
    independent_expected_panels = expected.panels - expected_figure_panels
    if independent_expected_panels and not _subset_relation("panel", independent_expected_panels, observed.panels | {item.panel for item in observed.figures if item.panel}, reasons, components):
        return False, (0, 0, 0, 0, 0, 0, 0), reasons, components
    if expected.cell_ranges and not _subset_relation("cell_range", expected.cell_ranges, observed.cell_ranges, reasons, components):
        return False, (0, 0, 0, 0, 0, 0, 0), reasons, components
    dimensions = (
        ("page", expected.pages, observed.pages),
        ("table", expected.tables, observed.tables),
        ("sheet", expected.sheets, observed.sheets),
        ("column", expected.columns, observed.columns),
        ("row", expected.rows, observed.rows),
        ("section", expected.sections, observed.sections),
        ("paragraph", expected.paragraphs, observed.paragraphs),
        ("timepoint", expected.timepoints, observed.timepoints),
    )
    for name, wanted, actual in dimensions:
        if not _subset_relation(name, wanted, actual, reasons, components):
            return False, (0, 0, 0, 0, 0, 0, 0), reasons, components
    if expected.terms and not _subset_relation("term", expected.terms, observed.terms, reasons, components):
        return False, (0, 0, 0, 0, 0, 0, 0), reasons, components
    if not _region_relation(expected, observed, reasons, components):
        return False, (0, 0, 0, 0, 0, 0, 0), reasons, components

    positive_expected = (
        bool(expected.files or expected.pages or expected.figures or expected.panels or expected.tables or expected.sheets or expected.columns or expected.rows or expected.sections or expected.paragraphs or expected.timepoints or expected.terms or expected.regions)
    )
    positive_observed = bool(observed.files or observed.pages or observed.figures or observed.panels or observed.tables or observed.sheets or observed.columns or observed.rows or observed.sections or observed.paragraphs or observed.timepoints or observed.terms or observed.regions)
    if not positive_expected or not positive_observed:
        reasons.append("generic location terms cannot establish a match")
        return False, (0, 0, 0, 0, 0, 0, 0), reasons, components

    exact_file_panel = int(bool(components.get("file_exact")))
    panel_score = int(bool(components.get("figure_panel_exact") or components.get("panel_agree")))
    structured_score = sum(int(components.get(f"{name}_agree", False)) for name in ("page", "table", "sheet", "column", "row", "cell_range", "section", "paragraph", "timepoint"))
    parent_score = int(bool(components.get("parent_figure")))
    term_score = int(bool(expected.terms and components.get("term_agree")))
    region_score = int(float(components.get("region_overlap", 0.0)) * 1000)
    score = (0, exact_file_panel, panel_score, structured_score, parent_score, term_score, region_score)
    reasons.append("at least one concrete location component agrees")
    return True, score, reasons, components


def _stable_id(item: Mapping[str, Any], *, label: bool) -> str:
    value = _field(item, "label_id", "observation_id", "id") if label else _field(item, "observation_id", "observation_id", "id")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("items require a non-empty stable id")
    return value


def label_observation_compatible(label: Mapping[str, Any], observation: Mapping[str, Any]) -> Compatibility:
    """Compare one expected label and one normalized observation without mutating either."""

    if not isinstance(label, Mapping) or not isinstance(observation, Mapping):
        raise ValueError("label and observation must be objects")
    label_family = label.get("issue_family")
    observation_family = observation.get("issue_family")
    if not isinstance(label_family, str) or not isinstance(observation_family, str):
        raise ValueError("issue_family must be a string")
    compatible_families = label.get("compatible_issue_families", ())
    if not isinstance(compatible_families, (list, tuple, set, frozenset)):
        raise ValueError("compatible_issue_families must be a list")
    issue_compatible = observation_family == label_family or observation_family in compatible_families
    expected = _parse_location(label.get("location"))
    observed = _parse_location(observation.get("location"))
    location_compatible, location_score, reasons, components = _location_compare(expected, observed)
    label_risk = _risk(label.get("risk_range"), label=True)
    observation_risk = _risk(observation.get("risk_level"))
    assert isinstance(label_risk, tuple) and isinstance(observation_risk, int)
    risk_compatible = label_risk[0] <= observation_risk <= label_risk[1]
    components["issue_family_exact"] = observation_family == label_family
    components["issue_family_allowed"] = issue_compatible
    components["risk_in_range"] = risk_compatible
    if issue_compatible:
        reasons.insert(0, "issue family is exact" if observation_family == label_family else "issue family is explicitly allowed")
    else:
        reasons.insert(0, "issue family is unrelated")
    reasons.append("risk is inside the inclusive label range" if risk_compatible else "risk is outside the inclusive label range; risk is scored separately")
    score = (int(observation_family == label_family),) + location_score[1:]
    return Compatibility(issue_compatible and location_compatible, issue_compatible, location_compatible, risk_compatible, score, tuple(reasons), dict(components))


@dataclass
class _FlowEdge:
    target: int
    reverse: int
    capacity: int
    cost: int
    label_id: str | None = None
    observation_id: str | None = None


def _add_flow_edge(graph: list[list[_FlowEdge]], source: int, target: int, capacity: int, cost: int, *, label_id: str | None = None, observation_id: str | None = None) -> _FlowEdge:
    forward = _FlowEdge(target, len(graph[target]), capacity, cost, label_id, observation_id)
    reverse = _FlowEdge(source, len(graph[source]), 0, -cost)
    graph[source].append(forward)
    graph[target].append(reverse)
    return forward


def _flow_solution(labels: Sequence[str], observations: Sequence[str], edges: Mapping[tuple[str, str], Match], target: int, forbidden: set[tuple[str, str]], *, score_base: int | None = None,) -> tuple[int, int, set[tuple[str, str]]]:
    if target < 0:
        return 0, 0, set()
    label_nodes = {item: index + 1 for index, item in enumerate(labels)}
    observation_offset = len(labels) + 1
    observation_nodes = {item: observation_offset + index for index, item in enumerate(observations)}
    sink = observation_offset + len(observations)
    graph: list[list[_FlowEdge]] = [[] for _ in range(sink + 1)]
    for label_id in labels:
        _add_flow_edge(graph, 0, label_nodes[label_id], 1, 0)
    for observation_id in observations:
        _add_flow_edge(graph, observation_nodes[observation_id], sink, 1, 0)
    if score_base is None:
        score_base = max((max(item.compatibility.score, default=0) for item in edges.values()), default=0) * max(len(labels), 1) + 2
        score_base = max(score_base, len(labels) + 2)
    def encoded(score: tuple[int, ...]) -> int:
        result = 0
        for item in score:
            result = result * score_base + item
        return result
    originals: list[tuple[str, str, _FlowEdge]] = []
    for (label_id, observation_id), match in sorted(edges.items()):
        if label_id not in label_nodes or observation_id not in observation_nodes or (label_id, observation_id) in forbidden:
            continue
        edge = _add_flow_edge(graph, label_nodes[label_id], observation_nodes[observation_id], 1, -encoded(match.compatibility.score), label_id=label_id, observation_id=observation_id)
        originals.append((label_id, observation_id, edge))
    flow = 0
    total_cost = 0
    while flow < target:
        distances: list[int | None] = [None] * len(graph)
        previous: list[tuple[int, int] | None] = [None] * len(graph)
        distances[0] = 0
        for _ in range(len(graph)):
            changed = False
            for node, distance in enumerate(distances):
                if distance is None:
                    continue
                for edge_index, edge in enumerate(graph[node]):
                    if edge.capacity <= 0:
                        continue
                    candidate = distance + edge.cost
                    if distances[edge.target] is None or candidate < distances[edge.target]:
                        distances[edge.target] = candidate
                        previous[edge.target] = (node, edge_index)
                        changed = True
            if not changed:
                break
        if distances[sink] is None:
            break
        node = sink
        while node:
            previous_item = previous[node]
            assert previous_item is not None
            parent, edge_index = previous_item
            edge = graph[parent][edge_index]
            edge.capacity -= 1
            graph[node][edge.reverse].capacity += 1
            node = parent
        total_cost += distances[sink]
        flow += 1
    used = {(label_id, observation_id) for label_id, observation_id, edge in originals if edge.capacity == 0 and graph[edge.target][edge.reverse].capacity == 1}
    return flow, -total_cost, used


def _maximum_cardinality(labels: Sequence[str], observations: Sequence[str], edges: Mapping[tuple[str, str], Match]) -> int:
    matched: dict[str, str] = {}
    def visit(label_id: str, seen: set[str]) -> bool:
        for observation_id in sorted(observation for left, observation in edges if left == label_id):
            if observation_id in seen:
                continue
            seen.add(observation_id)
            if observation_id not in matched or visit(matched[observation_id], seen):
                matched[observation_id] = label_id
                return True
        return False
    return sum(visit(label_id, set()) for label_id in labels)


def match_labels(labels: Sequence[Mapping[str, Any]], observations: Sequence[Mapping[str, Any]], *, roles: Sequence[str] = ("recall_label",)) -> MatchResult:
    """Return a deterministic maximum-cardinality, maximum-semantic-score assignment."""

    if not isinstance(labels, Sequence) or isinstance(labels, (str, bytes)) or not isinstance(observations, Sequence) or isinstance(observations, (str, bytes)):
        raise ValueError("labels and observations must be sequences")
    if isinstance(roles, (str, bytes)) or not isinstance(roles, Sequence) or not roles:
        raise ValueError("roles must be a non-empty sequence of strings")
    if any(not isinstance(role, str) or not role.strip() for role in roles):
        raise ValueError("roles must be a non-empty sequence of non-empty strings")
    selected_roles = set(roles)
    all_label_ids: set[str] = set()
    label_records: dict[str, Mapping[str, Any]] = {}
    for item in labels:
        if not isinstance(item, Mapping):
            raise ValueError("labels must contain objects")
        identifier = _stable_id(item, label=True)
        if identifier in all_label_ids:
            raise ValueError("label ids must be unique")
        all_label_ids.add(identifier)
        label_records[identifier] = item
        _risk(item.get("risk_range"), label=True)
        _parse_location(item.get("location"))
    observation_records: dict[str, Mapping[str, Any]] = {}
    for item in observations:
        if not isinstance(item, Mapping):
            raise ValueError("observations must contain objects")
        identifier = _stable_id(item, label=False)
        if identifier in observation_records:
            raise ValueError("observation ids must be unique")
        observation_records[identifier] = item
        _risk(item.get("risk_level"))
        _parse_location(item.get("location"))
    eligible_labels = sorted(
        identifier
        for identifier, item in label_records.items()
        if item.get("role", item.get("evaluation_role", "recall_label")) in selected_roles
    )
    observation_ids = sorted(observation_records)
    candidate_edges: dict[tuple[str, str], Match] = {}
    for label_id in eligible_labels:
        for observation_id in observation_ids:
            compatibility = label_observation_compatible(label_records[label_id], observation_records[observation_id])
            if compatibility.compatible:
                candidate_edges[(label_id, observation_id)] = Match(label_id, observation_id, compatibility)
    cardinality = _maximum_cardinality(eligible_labels, observation_ids, candidate_edges)
    score_base = max((max(item.compatibility.score, default=0) for item in candidate_edges.values()), default=0) * max(len(eligible_labels), 1) + 2
    score_base = max(score_base, len(eligible_labels) + 2)
    flow, best_score, _ = _flow_solution(eligible_labels, observation_ids, candidate_edges, cardinality, set(), score_base=score_base)
    if flow != cardinality:
        raise ValueError("assignment solver could not satisfy maximum cardinality")

    fixed: set[tuple[str, str]] = set()
    used_observations: set[str] = set()
    remaining_labels = list(eligible_labels)
    fixed_score = 0
    base = score_base
    def encoded(score: tuple[int, ...]) -> int:
        result = 0
        for item in score:
            result = result * base + item
        return result
    for label_id in eligible_labels:
        remaining_labels.remove(label_id)
        options = sorted(observation_id for left, observation_id in candidate_edges if left == label_id and observation_id not in used_observations)
        options.append("")
        choice_found = False
        for option in options:
            candidate_score = 0
            remaining_observations = [item for item in observation_ids if item not in used_observations and item != option]
            target = cardinality - len(fixed) - (1 if option else 0)
            if target < 0:
                continue
            if option:
                candidate = candidate_edges[(label_id, option)]
                candidate_score = encoded(candidate.compatibility.score)
            possible_flow, possible_score, _ = _flow_solution(remaining_labels, remaining_observations, candidate_edges, target, set(), score_base=score_base)
            if possible_flow == target and fixed_score + candidate_score + possible_score == best_score:
                choice_found = True
                if option:
                    fixed.add((label_id, option))
                    used_observations.add(option)
                    fixed_score += candidate_score
                break
        if not choice_found:
            raise ValueError("assignment tie-break could not preserve the optimum")
    selected_matches = tuple(candidate_edges[pair] for pair in sorted(fixed))
    ambiguous = False
    for pair in fixed:
        alternative_flow, alternative_score, _ = _flow_solution(eligible_labels, observation_ids, candidate_edges, cardinality, {pair}, score_base=score_base)
        if alternative_flow == cardinality and alternative_score == best_score:
            ambiguous = True
            break
    matched_labels = {item.label_id for item in selected_matches}
    matched_observations = {item.observation_id for item in selected_matches}
    return MatchResult(
        matches=selected_matches,
        unmatched_label_ids=tuple(item for item in eligible_labels if item not in matched_labels),
        unmatched_observation_ids=tuple(item for item in observation_ids if item not in matched_observations),
        candidate_edges=tuple(candidate_edges[pair] for pair in sorted(candidate_edges)),
        assignment_ambiguous=ambiguous,
    )


maximum_cardinality_matching = match_labels


__all__ = [
    "Compatibility",
    "Match",
    "MatchResult",
    "label_observation_compatible",
    "match_labels",
    "maximum_cardinality_matching",
]
