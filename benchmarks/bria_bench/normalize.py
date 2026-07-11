"""Normalize producer audit artifacts into the BRIA-Bench observation contract."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .contracts import validate_contract


_REQUIRED_ARTIFACTS = (
    "AUDIT_JSON_SUMMARY.json",
    "coverage.json",
    "pipeline_summary.json",
)
_RISK_LEVELS = {"R0", "R1", "R2", "R3", "R4"}
_DOMAIN_ROUTE_KEYS = (
    "candidate_type",
    "contextual_tag",
    "finding_type",
    "evidence_type",
)
_CONTROLLED_RISK_ROUTE_KEYS = ("risk_cap_tags",)
_PRIMARY_FAMILY_VALUES = {
    "audit_coverage_gap": "material_or_coverage_gap",
    "source_data_extraction_gap": "material_or_coverage_gap",
    "external_literature_search_gap": "material_or_coverage_gap",
    "unresolved_fig_raw_similarity": "material_or_coverage_gap",
    "unreadable_image_file": "material_or_coverage_gap",
    "unsupported_relevant_file": "material_or_coverage_gap",
    "image_reuse_cluster": "image_global_similarity",
    "image_similarity_candidate": "image_global_similarity",
    "global_image_similarity": "image_global_similarity",
    "image_global_similarity": "image_global_similarity",
    "global_near_duplicate": "image_global_similarity",
    "image_global_near_duplicate": "image_global_similarity",
    "local_patch_reuse": "image_local_reuse",
    "image_local_reuse": "image_local_reuse",
    "same_image_copy_move": "image_copy_move",
    "image_copy_move": "image_copy_move",
    "keypoint_geometric_match": "image_keypoint_geometry",
    "image_keypoint_geometry": "image_keypoint_geometry",
    "splice_forensics_triage_signal": "image_splice_forensics_triage",
    "image_splice_forensics_triage": "image_splice_forensics_triage",
    "channel_metadata_verification_gap": "image_channel_metadata_gap",
    "image_channel_metadata_gap": "image_channel_metadata_gap",
    "stats_consistency_candidate": "statistics_or_numeric",
    "numeric_consistency_candidate": "statistics_or_numeric",
    "statistical_consistency_candidate": "statistics_or_numeric",
    "weak_statistical_signal": "statistics_or_numeric",
    "pseudoreplication": "statistics_or_numeric",
    "pseudoreplication_candidate": "statistics_or_numeric",
    "text_overlap": "text_overlap",
    "text_overlap_candidate": "text_overlap",
    "package_internal_text_overlap": "text_overlap",
    "methods_boilerplate_overlap": "text_overlap",
    "self_overlap_candidate": "text_overlap",
    "external_text_match_candidate": "text_overlap",
    "methodology_or_reporting": "methodology_or_reporting",
    "methodology_readiness": "methodology_or_reporting",
}
_MATERIAL_ROUTE_MARKERS = (
    "audit_coverage_gap",
    "coverage_gap",
    "source_data_extraction_gap",
    "external_literature_search_gap",
    "unresolved_fig_raw_similarity",
    "unreadable",
    "unsupported",
    "missing_material",
    "missing material",
    "missing",
    "completeness",
    "material gap",
)
_LOCATION_FIELDS = {
    "text",
    "terms",
    "file",
    "page",
    "figure",
    "panel",
    "table",
    "sheet",
    "columns",
    "rows",
    "region",
}
_FAILURE_KEYS = (
    "producer_failures",
    "technical_failures",
    "failures",
    "errors",
)
_TECHNICAL_WORDS = re.compile(
    r"(?:\btechnical\b|\bexecution[_ -]?failure\b|\bdetector[_ -]?failure\b|\bcalibration\b|"
    r"\breport(?:[_ -]?assembly)?\b|\bpipeline[_ -]?failure\b|\btimed?[_ -]?out\b|"
    r"\bworkstream[_ -]?failed\b|\bproducer[_ -]?failure\b)",
    re.IGNORECASE,
)
_ABSOLUTE_STAGING = re.compile(
    r"/(?:[^/\s\"'<>?&#]+/)*\.audit\.staging-[^/\s\"'<>?&#]+"
)


class _ProducerArtifactError(ValueError):
    """Raised when a producer artifact is not strict, bounded JSON."""


def _strict_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _ProducerArtifactError(f"duplicate object key: {key}")
        result[key] = value
    return result


def _strict_parse_constant(value: str) -> Any:
    raise _ProducerArtifactError(f"non-finite JSON constant: {value}")


def _strict_parse_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise _ProducerArtifactError("non-finite JSON number")
    return parsed


def _strict_json_loads(text: str) -> Any:
    return json.loads(
        text,
        object_pairs_hook=_strict_object_pairs,
        parse_constant=_strict_parse_constant,
        parse_float=_strict_parse_float,
    )


def _exceeds_json_depth(value: Any, maximum: int = 512) -> bool:
    pending: list[tuple[Any, int]] = [(value, 0)]
    while pending:
        current, depth = pending.pop()
        if depth > maximum:
            return True
        if isinstance(current, dict):
            pending.extend((child, depth + 1) for child in current.values())
        elif isinstance(current, list):
            pending.extend((child, depth + 1) for child in current)
    return False
_BOUNDARY_TERM_PATTERNS = (
    (
        "fraud",
        re.compile(
            r"\b(?:authors?|researchers?|research\s+team|study\s+group|investigators?)\b"
            r"\s+(?:(?:committed|commit)\s+|(?:have|has)\s+committed\s+|(?:were|was)\s+found\s+to\s+have\s+committed\s+)"
            r"(?:research\s+)?fraud\b"
            r"|\b(?:authors?|researchers?)\b\s+(?:are|were)\s+guilty\s+of\s+(?:research\s+)?fraud\b"
            r"|\b(?:evidence|review|investigation)\b\s+(?:confirms?|establishes?|proves?)\s+that\s+"
            r"(?:the\s+)?(?:authors?|researchers?)\s+(?:(?:committed|commit)|(?:have|has)\s+committed|(?:were|was)\s+found\s+to\s+have\s+committed)\s+"
            r"(?:research\s+)?fraud\b",
            re.IGNORECASE,
        ),
    ),
    (
        "misconduct",
        re.compile(
            r"\b(?:authors?|researchers?|research\s+team|study\s+group|investigators?)\b"
            r"\s+(?:(?:committed|commit)\s+|(?:have|has)\s+committed\s+|(?:were|was)\s+found\s+to\s+have\s+committed\s+)"
            r"(?:research\s+)?misconduct\b"
            r"|\b(?:authors?|researchers?)\b\s+(?:are|were)\s+guilty\s+of\s+(?:research\s+)?misconduct\b"
            r"|\b(?:authors?|researchers?|research\s+team|study\s+group|investigators?)\b\s+"
            r"engaged\s+in\s+(?:research\s+)?misconduct\b"
            r"|\b(?:evidence|review|investigation)\b\s+(?:confirms?|establishes?|proves?)\s+that\s+"
            r"(?:the\s+)?(?:authors?|researchers?)\s+(?:(?:committed|commit)|(?:have|has)\s+committed|(?:were|was)\s+found\s+to\s+have\s+committed)\s+"
            r"(?:research\s+)?misconduct\b",
            re.IGNORECASE,
        ),
    ),
    (
        "fabrication",
        re.compile(
            r"\b(?:authors?|researchers?|research\s+team|study\s+group|investigators?)\b\s+"
            r"(?:fabricated)\s+(?:the\s+)?(?:data|results?|figures?)\b"
            r"|\b(?:data|results?|figures?)\b\s+(?:were|are|have\s+been|has\s+been|had\s+been)\s+fabricated\b"
            r"|\b(?:evidence|review|investigation)\b\s+(?:confirms?|establishes?|proves?)\s+that\s+"
            r"(?:the\s+)?(?:authors?|researchers?)\s+(?:fabricated|have\s+fabricated|were\s+found\s+to\s+have\s+fabricated)\s+(?:the\s+)?(?:data|results?|figures?)\b"
            r"|\b(?:evidence|review|investigation)\b\s+(?:confirms?|establishes?|proves?)\s+that\s+"
            r"(?:the\s+)?(?:data|results?|figures?)\s+(?:were|are|have\s+been|has\s+been|had\s+been)\s+fabricated\b",
            re.IGNORECASE,
        ),
    ),
    (
        "falsification",
        re.compile(
            r"\b(?:authors?|researchers?|research\s+team|study\s+group|investigators?)\b\s+"
            r"(?:falsified)\s+(?:the\s+)?(?:data|results?|figures?)\b"
            r"|\b(?:data|results?|figures?)\b\s+(?:were|are|have\s+been|has\s+been|had\s+been)\s+falsified\b"
            r"|\b(?:evidence|review|investigation)\b\s+(?:confirms?|establishes?|proves?)\s+that\s+"
            r"(?:the\s+)?(?:authors?|researchers?)\s+(?:falsified|have\s+falsified|were\s+found\s+to\s+have\s+falsified)\s+(?:the\s+)?(?:data|results?|figures?)\b"
            r"|\b(?:evidence|review|investigation)\b\s+(?:confirms?|establishes?|proves?)\s+that\s+"
            r"(?:the\s+)?(?:data|results?|figures?)\s+(?:were|are|have\s+been|has\s+been|had\s+been)\s+falsified\b",
            re.IGNORECASE,
        ),
    ),
    (
        "integrity conclusion",
        re.compile(
            r"\b(?:integrity|certificate|certification)\b"
            r".{0,40}\b(?:status|check|conclusion|result|certificate|certification)\b"
            r".{0,20}\b(?:pass(?:ed)?|fail(?:ed)?|clean|certified)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "integrity conclusion",
        re.compile(r"\bpass(?:ed)?\s+integrity\s+audit\b|\bfail(?:ed)?\s+integrity\s+audit\b", re.IGNORECASE),
    ),
    (
        "integrity conclusion",
        re.compile(r"\bintegrity\s+audit\s*[:=]\s*(?:pass(?:ed)?|fail(?:ed)?|clean|certified)\b", re.IGNORECASE),
    ),
    (
        "integrity conclusion",
        re.compile(r"\b(?:certificate|certification)\s*[:=]\s*(?:pass(?:ed)?|fail(?:ed)?|clean|certified)\b", re.IGNORECASE),
    ),
    (
        "integrity conclusion",
        re.compile(r"\bmanuscript\b.{0,30}\b(?:is|status|conclusion|result)\b.{0,20}\b(?:pass(?:ed)?|fail(?:ed)?|clean|certified)\b", re.IGNORECASE),
    ),
    ("author misconduct", re.compile(r"(?:作者|研究团队|研究人员|课题组)(?:涉嫌|存在|实施|进行了|被证实)?(?:学术不端|造假|伪造|篡改|欺诈)")),
    ("research misconduct", re.compile(r"(?:存在|属于|构成)(?:严重)?学术不端")),
    ("data falsification", re.compile(r"数据(?:被)?(?:造假|伪造|篡改)")),
)
_BOUNDARY_NEGATIONS = (
    re.compile(r"\bnot\s+(?:a\s+)?misconduct(?:\s+or\s+[a-z-]+)?\s+(?:verdict|finding|conclusion)\b", re.I),
    re.compile(r"\bnot\s+(?:evidence|proof)\s+of\s+(?:misconduct|fraud|falsification|fabrication)\b", re.I),
    re.compile(r"\bnot\s+a\s+verdict\s+of\s+(?:misconduct|fraud)\b", re.I),
    re.compile(r"\bdoes\s+not\s+(?:determine|establish|prove)\s+misconduct\b", re.I),
    re.compile(r"\bdoes\s+not\s+(?:determine|establish|prove)\s+(?:fraud|falsification|fabrication)\b", re.I),
    re.compile(r"\b(?:does|do|did|cannot|could not)\s+(?:find|establish|determine|prove|constitute|represent)\s+(?:misconduct|fraud|falsification|fabrication)\b", re.I),
    re.compile(r"\b(?:(?:does|do|did)\s+not|cannot|could not)\s+(?:find|establish|determine|prove)\s+[^.!?\n]{0,60}\bauthor(?:s)?\s+(?:guilt|guilty)\b", re.I),
    re.compile(r"\bcannot\s+(?:determine|establish|prove)\s+misconduct\b", re.I),
    re.compile(r"\bno\s+findings?\s+(?:is|are)\s+not\s+a\s+clean[- ]manuscript\s+verdict\b", re.I),
    re.compile(r"\bnot\s+a\s+clean[- ]manuscript\s+verdict\b", re.I),
    re.compile(r"\bnot\s+[^.!?\n]{0,80}\b(?:misconduct|fraud)\s+(?:verdict|finding|conclusion)\b", re.I),
    re.compile(r"\bnot\s+(?:a\s+)?(?:clean|certified)\s+(?:manuscript|integrity|result|conclusion)\b", re.I),
    re.compile(r"\bnot\s+certified\s+clean\b", re.I),
    re.compile(r"\bnot\s+certified[- ]clean\b", re.I),
    re.compile(r"\b(?:no\s+evidence\s+of|do(?:es)?\s+not\s+allege|did\s+not\s+allege)\s+(?:fraud|misconduct|fabrication|falsification)\b", re.I),
    re.compile(r"\b(?:authors?|researchers?|research\s+team|study\s+group)\b\s+(?:deny|denies|denied|report|reported|state|stated|claim|claimed|allege|alleged)\s+(?:that\s+)?[^.!?\n;]{0,140}\b(?:fraud|misconduct|fabricat(?:ed|ion)|falsif(?:ied|ication))\b", re.I),
    re.compile(r"\bit\s+was\s+(?:alleged|reported)\s+that\b[^.!?\n;]{0,140}\b(?:fraud|misconduct|fabricat(?:ed|ion)|falsif(?:ied|ication))\b", re.I),
    re.compile(r"\baccording\s+to\b[^.!?\n;]{0,140}\b(?:fraud|misconduct|fabricat(?:ed|ion)|falsif(?:ied|ication))\b", re.I),
    re.compile(r"\b(?:data|results?|figures?)\b\s+(?:were|are|have\s+been|has\s+been|had\s+been)\s+not\s+(?:fabricated|falsified)\b", re.I),
    re.compile(r"\b(?:integrity\s+)?certificate\s+(?:generation|creation|execution|verification)\s+(?:failed|error|crashed)\b", re.I),
    re.compile(r"\bintegrity(?:\s+audit)?\s+(?:check|audit)?\s+fail(?:ed)?\s+to\s+(?:run|execute|start|complete)\b", re.I),
    re.compile(r"\bintegrity(?:\s+audit)?\s+(?:check|audit)?\s+fail(?:ed)?\s+(?:because|due|from)\b", re.I),
    re.compile(r"\b(?:do|does|did|should)\s+not\s+say\s+(?:fraud|fraudulent|misconduct)\b", re.I),
    re.compile(r"\bsay\s+this\s+paper\s+is\s+fraudulent\b", re.I),
    re.compile(r"\b(?:quoted|prompt[- ]?injection|manual\s+instruction|instruction)\b", re.I),
    re.compile(r"不构成(?:学术不端|欺诈|造假)(?:结论|认定)?", re.I),
    re.compile(r"(?:不能|无法|不应|不得|不要).{0,12}(?:判定|认定|说).{0,12}(?:学术不端|欺诈|造假)", re.I),
    re.compile(r"(?:没有发现|无发现).{0,12}(?:不等于|并不表示).{0,12}(?:论文)?(?:清白|无问题)", re.I),
    re.compile(r"(?:不代表|不证明|不能证明).{0,12}(?:学术不端|欺诈|造假)", re.I),
    re.compile(r"(?:未|不曾|没有).{0,8}(?:认定|判定|证明).{0,8}(?:学术不端|欺诈|造假)", re.I),
    re.compile(r"(?:不|未)存在学术不端", re.I),
    re.compile(r"(?:研究团队|研究人员|课题组|作者)(?:没有|未|不曾|并非).{0,8}(?:造假|伪造|篡改|学术不端)", re.I),
    re.compile(r"(?:研究团队|研究人员|课题组|作者)(?:没有|未|不曾)被证实(?:造假|伪造|篡改|存在学术不端)", re.I),
    re.compile(r"(?:据报道|据称|作者称|作者否认).{0,40}(?:造假|伪造|篡改|学术不端)", re.I),
)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _path_value(value: object, label: str, *, must_exist: bool = True) -> Path:
    if not isinstance(value, (str, Path)):
        raise ValueError(f"{label} must be a path")
    if not str(value).strip():
        raise ValueError(f"{label} must not be empty")
    try:
        path = Path(value).expanduser().absolute()
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid {label}") from exc
    if must_exist and (not path.exists() or not path.is_dir()):
        raise ValueError(f"{label} must be an existing directory")
    return path


def _add_contract_error(errors: list[dict[str, str]], message: str, path: str) -> None:
    errors.append({"message": message, "schema": "producer artifact", "path": path})


def _load_json_artifact(
    output_dir: Path,
    name: str,
    contract_errors: list[dict[str, str]],
    failures: list[tuple[dict[str, Any], bool]],
) -> dict[str, Any] | None:
    path = output_dir / name
    if not path.is_file():
        message = f"Missing required producer artifact: {name}."
        _add_contract_error(contract_errors, message, name)
        failures.append((_failure_record("producer", "missing_artifact", message, name), False))
        return None
    try:
        value = _strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, OverflowError, RecursionError) as exc:
        message = f"Malformed producer artifact {name}: {type(exc).__name__}."
        _add_contract_error(contract_errors, message, name)
        failures.append((_failure_record("producer", "malformed_artifact", message, name), False))
        return None
    if not isinstance(value, dict) or _exceeds_json_depth(value):
        message = f"Malformed producer artifact {name}: top-level JSON value must be an object."
        if isinstance(value, dict):
            message = f"Malformed producer artifact {name}: JSON nesting exceeds the supported depth."
        _add_contract_error(contract_errors, message, name)
        failures.append((_failure_record("producer", "malformed_artifact", message, name), False))
        return None
    return value


def _failure_record(
    module: str,
    failure_type: str,
    message: str,
    source: str,
    *,
    category: str = "",
    status: str = "",
    returncode: int | None = None,
    timed_out: bool | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "module": module.strip() or "producer",
        "failure_type": failure_type.strip() or "failure",
        "message": message,
        "source": source,
    }
    if category.strip():
        record["category"] = category.strip()
    if status.strip():
        record["status"] = status.strip()
    if returncode is not None:
        record["returncode"] = returncode
    if timed_out is not None:
        record["timed_out"] = bool(timed_out)
    return record


def _failure_from_value(
    value: Any,
    source: str,
    *,
    default_module: str = "producer",
    default_type: str = "failure",
    disclosed: bool = False,
) -> tuple[dict[str, Any], bool] | None:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if ":" in text:
            module, detail = text.split(":", 1)
            module, detail = module.strip(), detail.strip()
            if module and detail:
                return _failure_record(module, default_type if not detail else detail, text, source), disclosed
        return _failure_record(default_module, default_type, text, source), disclosed
    if not isinstance(value, dict):
        return None
    if not value or not any(
        key in value
        for key in (
            "module",
            "detector",
            "name",
            "failure_type",
            "failure",
            "error_type",
            "message",
            "detail",
            "error",
            "category",
            "status",
            "returncode",
            "timed_out",
        )
    ):
        return None
    module_value = value.get("module", value.get("detector", value.get("name", default_module)))
    module = str(module_value).strip() if module_value is not None else default_module
    type_value = value.get("failure_type", value.get("failure", value.get("error_type", "")))
    failure_type = str(type_value).strip() if type_value else default_type
    message_value = value.get("message", value.get("detail", value.get("error", "")))
    message = str(message_value).strip() if message_value else _canonical(value)
    category = str(value.get("category", "")).strip()
    status = str(value.get("status", "")).strip()
    returncode = value.get("returncode")
    if not isinstance(returncode, int) or isinstance(returncode, bool):
        returncode = None
    timed_out = value.get("timed_out") if isinstance(value.get("timed_out"), bool) else None
    return (
        _failure_record(
            module,
            failure_type,
            message,
            source,
            category=category,
            status=status,
            returncode=returncode,
            timed_out=timed_out,
        ),
        disclosed,
    )


def _failure_identity(record: dict[str, Any]) -> tuple[Any, ...]:
    message = re.sub(r"\s+", " ", str(record.get("message", "")).strip().lower())
    semantic = message
    if re.search(r"\b(?:timed?\s*out|timeout)\b", message):
        detail = re.sub(r"\b(?:timed?\s*out|timeout)\b", "", message)
        detail = re.sub(r"\b(?:failure|error|detector|occurred|was|is)\b", "", detail)
        detail = re.sub(r"\b[a-z0-9_.-]+\s*:\s*", "", detail)
        detail = re.sub(r"\s+", " ", detail).strip(" .,:;-")
        semantic = "timeout" + (f":{detail}" if detail else "")
    elif re.search(r"\b(?:permission|access)\b.{0,24}\b(?:denied|error|failure)\b", message):
        detail = re.sub(r"\b(?:permission|access|denied|error|failure)\b", "", message)
        detail = re.sub(r"\b[a-z0-9_.-]+\s*:\s*", "", detail)
        detail = re.sub(r"\s+", " ", detail).strip(" .,:;-")
        semantic = "permission_access" + (f":{detail}" if detail else "")
    elif re.search(r"\b(?:failed?\s+to\s+(?:run|execute|start)|execution\s+failure)\b", message):
        semantic = "execution_failure"
    identity = tuple(record.get(key) for key in ("module", "failure_type", "category", "status", "returncode", "timed_out"))
    identity += (semantic,)
    if record.get("failure_type") in {"missing_artifact", "malformed_artifact", "malformed_failure_entry"}:
        return identity + (record.get("source"),)
    return identity


def _dedupe_failures(entries: list[tuple[dict[str, Any], bool]]) -> tuple[list[dict[str, Any]], set[tuple[Any, ...]]]:
    grouped: dict[tuple[Any, ...], list[tuple[dict[str, Any], bool]]] = {}
    for record, disclosed in entries:
        grouped.setdefault(_failure_identity(record), []).append((record, disclosed))
    selected: list[dict[str, Any]] = []
    disclosed_ids: set[tuple[Any, ...]] = set()
    for identity in sorted(grouped, key=lambda item: _canonical(item)):
        candidates = grouped[identity]
        if any(disclosed for _, disclosed in candidates):
            disclosed_ids.add(identity)
        selected.append(
            sorted(
                (record for record, _ in candidates),
                key=lambda record: (-len(record), _canonical(record)),
            )[0]
        )
    return selected, disclosed_ids


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _issue_family(finding: dict[str, Any]) -> str:
    def values_for(keys: tuple[str, ...]) -> list[str]:
        values: list[str] = []
        for key in keys:
            value = finding.get(key)
            if isinstance(value, str):
                values.append(value)
            elif isinstance(value, list):
                values.extend(item for item in value if isinstance(item, str))
        return values

    def exact_family(values: list[str]) -> str | None:
        for value in values:
            normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
            if normalized in _PRIMARY_FAMILY_VALUES:
                return _PRIMARY_FAMILY_VALUES[normalized]
            if any(
                marker in normalized or marker.replace("_", " ") in value.lower()
                for marker in _MATERIAL_ROUTE_MARKERS
            ):
                return "material_or_coverage_gap"
        return None

    domain_values = values_for(_DOMAIN_ROUTE_KEYS)
    domain_family = exact_family(domain_values)
    if domain_family is not None:
        return domain_family
    controlled_risk_values = values_for(_CONTROLLED_RISK_ROUTE_KEYS)
    controlled_risk_family = exact_family(controlled_risk_values)
    if controlled_risk_family is not None:
        return controlled_risk_family

    text = " ".join(
        str(finding.get(key, ""))
        for key in (
            "detector",
            "module",
            "candidate_type",
            "contextual_tag",
            "risk_cap_tags",
            "finding_type",
            "evidence_type",
        )
    ).lower()
    if (
        "image_reuse_cluster" in text
        or "image reuse cluster" in text
        or "global" in text and ("near duplicate" in text or "similarity" in text or "reuse cluster" in text)
    ):
        return "image_global_similarity"
    if "local_patch" in text or "local patch" in text:
        return "image_local_reuse"
    if "copy_move" in text or "copy-move" in text or "copy move" in text:
        return "image_copy_move"
    if "keypoint" in text or "geometric" in text:
        return "image_keypoint_geometry"
    if "splice" in text or "jpeg ghost" in text or "noise-cfa" in text or "noise cfa" in text:
        return "image_splice_forensics_triage"
    if "channel_metadata" in text or "channel metadata" in text or "ome" in text:
        return "image_channel_metadata_gap"
    if any(
        term in text
        for term in (
            "stat",
            "numeric",
            "digit",
            "sd-sem",
            "sd sem",
            "sd/sem",
            "standard deviation",
            "standard error",
            "pseudoreplication",
        )
    ):
        return "statistics_or_numeric"
    if "text_overlap" in text or "text overlap" in text or "internal text" in text or "package text" in text:
        return "text_overlap"
    if any(term in text for term in ("methodology", "reporting", "readiness", "reporting standard")):
        return "methodology_or_reporting"
    if any(term in text for term in ("missing", "unsupported", "unreadable", "coverage", "completeness", "material")):
        return "material_or_coverage_gap"
    return "other_reviewable_observation"


def _is_technical_finding(finding: dict[str, Any]) -> bool:
    text = " ".join(
        str(finding.get(key, ""))
        for key in (
            "detector",
            "module",
            "candidate_type",
            "contextual_tag",
            "finding_type",
            "evidence_type",
        )
    ).lower().replace("_", " ")
    return bool(_TECHNICAL_WORDS.search(text))


def _location(value: Any) -> dict[str, Any] | str | None:
    if isinstance(value, str) and value.strip():
        return value
    if not isinstance(value, dict) or not value or any(key not in _LOCATION_FIELDS for key in value):
        return None
    return copy.deepcopy(value)


def _record_malformed_finding(
    index: int,
    message: str,
    contract_errors: list[dict[str, str]],
    technical_entries: list[tuple[dict[str, Any], bool]],
) -> None:
    path = f"AUDIT_JSON_SUMMARY.json.findings[{index}]"
    _add_contract_error(contract_errors, message, path)
    technical_entries.append((_failure_record("producer", "malformed_finding", message, path), False))


def _normalize_finding(
    finding: dict[str, Any],
    contract_errors: list[dict[str, str]],
    technical_entries: list[tuple[dict[str, Any], bool]],
    index: int,
) -> dict[str, Any] | None:
    if any(
        str(finding.get(key, "")).strip().lower() == "expected_traceability"
        for key in ("candidate_type", "contextual_tag", "finding_type", "evidence_type")
    ):
        return None
    if _is_technical_finding(finding):
        module = str(finding.get("module", finding.get("detector", "producer")))
        failure_type = str(finding.get("finding_type", "producer failure"))
        message = str(finding.get("summary", finding.get("message", failure_type)))
        technical_entries.append((_failure_record(module, failure_type, message, "AUDIT_JSON_SUMMARY.json"), True))
        return None

    result: dict[str, Any] = {}
    source_id = finding.get("finding_id", finding.get("source_finding_id"))
    if isinstance(source_id, str) and source_id.strip():
        result["source_finding_id"] = source_id
    detector = finding.get("detector", finding.get("source_detector", finding.get("module")))
    if isinstance(detector, str) and detector.strip():
        result["source_detector"] = detector
    finding_type = finding.get("finding_type", finding.get("type"))
    if isinstance(finding_type, str) and finding_type.strip():
        result["finding_type"] = finding_type
    location = _location(finding.get("location", finding.get("locations")))
    if location is None:
        _record_malformed_finding(index, "Finding has a missing or unsupported location.", contract_errors, technical_entries)
        return None
    result["location"] = location
    risk_level = finding.get("risk_level", finding.get("calibrated_risk_level"))
    if not isinstance(risk_level, str) or risk_level not in _RISK_LEVELS:
        _record_malformed_finding(index, "Finding has a missing or invalid risk_level.", contract_errors, technical_entries)
        return None
    result["risk_level"] = risk_level
    evidence_type = finding.get("evidence_type")
    if isinstance(evidence_type, str) and evidence_type.strip():
        result["evidence_type"] = evidence_type
    summary = finding.get("summary", finding.get("human_summary"))
    if isinstance(summary, str):
        result["summary"] = summary
    action = finding.get("recommended_action", finding.get("action"))
    if isinstance(action, str):
        result["recommended_action"] = action
    benign = finding.get("benign_explanations", finding.get("benign_explanations_considered"))
    benign_values = _string_list(benign)
    if benign_values:
        result["benign_explanations"] = benign_values
    materials = finding.get("required_materials", finding.get("required_materials_to_resolve"))
    material_values = _string_list(materials)
    if material_values:
        result["required_materials"] = material_values
    if isinstance(finding.get("benign_explanations_considered"), list) and "benign_explanations" not in result:
        values = _string_list(finding["benign_explanations_considered"])
        if values:
            result["benign_explanations_considered"] = values
    if isinstance(finding.get("required_materials_to_resolve"), list) and "required_materials" not in result:
        values = _string_list(finding["required_materials_to_resolve"])
        if values:
            result["required_materials_to_resolve"] = values
    source_artifact = finding.get("source_artifact")
    if isinstance(source_artifact, str) and source_artifact.strip():
        result["source_artifact"] = source_artifact
    confidence = finding.get("confidence")
    if "confidence" in finding:
        valid_confidence = False
        if isinstance(confidence, int) and not isinstance(confidence, bool):
            valid_confidence = 0 <= confidence <= 1
        elif isinstance(confidence, float):
            valid_confidence = math.isfinite(confidence) and 0 <= confidence <= 1
        if not valid_confidence:
            _record_malformed_finding(index, "Finding has an invalid confidence.", contract_errors, technical_entries)
            return None
        result["confidence"] = confidence
    result["issue_family"] = _issue_family(finding)
    return result


def _validate_candidate_observation(case_id: str, observation: dict[str, Any]) -> None:
    candidate = {
        "case_id": case_id,
        "observations": [dict(observation, observation_id="candidate")],
        "technical_failures": [],
        "reported_technical_failures": [],
        "boundary_violations": [],
        "contract_errors": [],
    }
    validate_contract("observation.schema.json", candidate)


def _walk_strings(value: Any, path: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key in sorted(value, key=str):
            child_path = f"{path}.{key}" if path else str(key)
            yield from _walk_strings(value[key], child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_strings(child, f"{path}[{index}]")


def _boundary_violations(
    report: str | None,
    artifacts: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    units: list[tuple[str, str, str]] = []
    if report is not None:
        for index, line in enumerate(report.splitlines(), 1):
            if line.strip():
                for clause in _boundary_text_units(line):
                    units.append(("audit-report.md", str(index), clause))
    for artifact_name, value in sorted(artifacts.items()):
        for path, text in _walk_strings(value, artifact_name):
            for clause in _boundary_text_units(text):
                units.append((artifact_name, path, clause))

    found: dict[tuple[str, str, str, str], dict[str, str]] = {}
    for source, location, text in units:
        for term, pattern in _BOUNDARY_TERM_PATTERNS:
            for match in pattern.finditer(text):
                if _boundary_match_is_negated(text, match):
                    continue
                matched_term = match.group(0)
                key = (source, location, term, text)
                found[key] = {
                    "message": text,
                    "source": source,
                    "term": matched_term,
                    "location": location,
                }
    return [found[key] for key in sorted(found)]


def _boundary_text_units(text: str) -> list[str]:
    units: list[str] = []
    for semicolon_clause in re.split(r";+", text):
        for sentence in re.split(r"(?<=[.!?。！？])\s+", semicolon_clause):
            if sentence.strip():
                units.append(sentence.strip())
    return units


def _boundary_match_is_negated(text: str, match: re.Match[str]) -> bool:
    for negative in _BOUNDARY_NEGATIONS:
        for candidate in negative.finditer(text):
            if candidate.start() <= match.end() and match.start() <= candidate.end():
                return True
    return False


def _report_clauses(report: str) -> list[str]:
    clauses: list[str] = []
    for line in report.splitlines():
        if not line.strip():
            continue
        for semicolon_clause in re.split(r";+", line):
            for sentence in re.split(r"(?<=[.!?。！？])\s+", semicolon_clause):
                if sentence.strip():
                    clauses.append(sentence.strip())
    return clauses


_FAILURE_NEGATIVE_POLARITY = (
    re.compile(r"\b(?:did|does|do|will|would)\s+not\s+fail(?:ed|ure)?\b", re.I),
    re.compile(r"\bno\s+(?:timeout|failure|error|unavailability)\s+(?:occurred|was|is|present)\b", re.I),
    re.compile(r"\b(?:did|does|do)\s+not\s+report\s+(?:a\s+)?(?:timeout|failure|error)\b", re.I),
    re.compile(r"\bno\s+evidence\s+of\s+(?:a\s+)?(?:timeout|failure|error)\b", re.I),
    re.compile(r"\bwithout\s+(?:a\s+)?(?:timeout|failure|error|unavailability)\b", re.I),
    re.compile(r"\b(?:completed|finished|succeeded|passed)\s+(?:successfully|without)\b", re.I),
    re.compile(r"\bsuccessfully\s+(?:completed|finished|ran)\b", re.I),
    re.compile(
        r"\b(?:timeout|failure|error)\s+(?:did\s+not\s+occur|was\s+not\s+(?:observed|detected|present)|not\s+(?:observed|detected|present))\b",
        re.I,
    ),
)
_FAILURE_AFFIRMATIVE_SEMANTICS = re.compile(
    r"\b(?:failed(?:\s+to)?|failure|error|timeout|timed\s+out|unavailable|"
    r"did\s+not\s+complete|could\s+not\s+complete|encountered\s+(?:an\s+)?error)\b",
    re.I,
)


def _failure_semantics_match(record: dict[str, Any], clause: str) -> bool:
    lowered = clause.lower()
    if any(pattern.search(lowered) for pattern in _FAILURE_NEGATIVE_POLARITY):
        return False
    failure_type = str(record.get("failure_type", "failure")).lower().replace("_", " ").replace("-", " ")
    is_timeout = "timeout" in failure_type or "timed out" in failure_type
    is_permission = "permission" in failure_type or "access" in failure_type
    if failure_type in lowered:
        return True
    normalized_type = failure_type.replace(" ", "_")
    if normalized_type in clause.lower():
        return True
    if is_permission:
        return bool(re.search(r"\b(?:permission|access)\b.{0,24}\b(?:denied|error|failure|unavailable)\b", lowered))
    if is_timeout:
        return bool(
            re.search(
                r"\b(?:timed?\s*out|timeout|failed?\s+to\s+(?:run|execute|start|complete)|did\s+not\s+complete|encountered\s+(?:an\s+)?error)\b",
                lowered,
            )
        )
    is_generic = any(
        term in failure_type
        for term in ("failure", "error", "execution", "failed", "unavailable", "malformed", "missing", "coverage gap")
    )
    return is_generic and bool(_FAILURE_AFFIRMATIVE_SEMANTICS.search(lowered))


def _report_discloses_failure(record: dict[str, Any], report: str) -> bool:
    module = str(record.get("module", "")).lower()
    leaf = module.rsplit(".", 1)[-1]

    def matches_identifier(identifier: str, clause: str) -> bool:
        if not identifier:
            return False
        pattern = re.compile(
            rf"(?<![A-Za-z0-9_.-]){re.escape(identifier)}(?![A-Za-z0-9_.-])",
            re.IGNORECASE,
        )
        return pattern.search(clause) is not None

    return any(
        (matches_identifier(module, clause) or matches_identifier(leaf, clause))
        and _failure_semantics_match(record, clause)
        for clause in _report_clauses(report)
    )


def _discover_staging_roots(value: Any) -> list[Path]:
    roots: list[Path] = []
    for _, text in _walk_strings(value):
        for match in _ABSOLUTE_STAGING.finditer(text):
            try:
                roots.append(Path(match.group(0)).absolute())
            except (OSError, RuntimeError, ValueError):
                continue
    return roots


def _file_uri_path(value: str) -> Path | None:
    parsed = urlparse(value)
    if parsed.scheme.lower() != "file" or parsed.netloc not in ("", "localhost"):
        return None
    try:
        return Path(unquote(parsed.path)).absolute()
    except (OSError, RuntimeError, TypeError, ValueError):
        return None


def _redact_text(text: str, roots: list[tuple[str, str]]) -> str:
    result = text
    for root, placeholder in sorted(roots, key=lambda item: (-len(item[0]), item[0], item[1])):
        pattern = re.compile(
            rf"(?<![A-Za-z0-9._-]){re.escape(root)}(?=$|[/\\\s\"'<>:;,.()\[\]?&#])"
        )
        result = pattern.sub(placeholder, result)
    return result


def _redact(value: Any, roots: list[tuple[str, str]]) -> Any:
    if isinstance(value, str):
        return _redact_text(value, roots)
    if isinstance(value, list):
        return [_redact(item, roots) for item in value]
    if isinstance(value, dict):
        return {_redact_text(str(key), roots): _redact(child, roots) for key, child in value.items()}
    return value


def _redaction_roots(
    output_dir: Path,
    package_root: Path | None,
    staging_roots: tuple[Path, ...],
    artifacts: dict[str, dict[str, Any]],
    report: str | None,
) -> list[tuple[str, str]]:
    roots: dict[str, str] = {}

    def add_root(path: Path, placeholder: str) -> None:
        candidates = {path, path.absolute()}
        lexical = path
        for _ in range(8):
            if not lexical.is_symlink():
                break
            try:
                target = Path(os.readlink(lexical))
            except (OSError, RuntimeError, ValueError):
                break
            lexical = target if target.is_absolute() else lexical.parent / target
            candidates.add(lexical.absolute())
        try:
            candidates.add(path.resolve())
        except (OSError, RuntimeError, ValueError):
            pass
        for candidate in candidates:
            roots[str(candidate)] = placeholder

    add_root(output_dir, "<OUTPUT_ROOT>")
    add_root(Path.home().resolve(), "<HOME>")
    if package_root is not None:
        add_root(package_root, "<PACKAGE_ROOT>")
    for root in staging_roots:
        add_root(root, "<STAGING_ROOT>")
    for value in artifacts.values():
        for root in _discover_staging_roots(value):
            add_root(root, "<STAGING_ROOT>")
    if report is not None:
        for root in _discover_staging_roots(report):
            add_root(root, "<STAGING_ROOT>")
    return list(roots.items())


def _record_malformed_failure_entry(
    message: str,
    path: str,
    contract_errors: list[dict[str, str]],
    technical_entries: list[tuple[dict[str, Any], bool]],
) -> None:
    _add_contract_error(contract_errors, message, path)
    technical_entries.append((_failure_record("producer", "malformed_failure_entry", message, path), False))


def normalize_audit_output(
    case_id: str,
    output_dir: str | Path,
    *,
    package_root: str | Path | None = None,
    staging_roots: Iterable[str | Path] = (),
) -> dict[str, object]:
    """Normalize one producer output directory into a validated observation payload."""
    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError("case_id must be a non-empty string")
    output_path = _path_value(output_dir, "output_dir")
    package_path = None if package_root is None else _path_value(package_root, "package_root")
    if isinstance(staging_roots, (str, bytes)):
        raise ValueError("staging_roots must be an iterable of paths")
    try:
        staging_paths = tuple(_path_value(root, "staging root", must_exist=False) for root in staging_roots)
    except TypeError as exc:
        raise ValueError("staging_roots must be an iterable of paths") from exc

    contract_errors: list[dict[str, str]] = []
    technical_entries: list[tuple[dict[str, Any], bool]] = []
    artifacts: dict[str, dict[str, Any]] = {}
    for name in _REQUIRED_ARTIFACTS:
        value = _load_json_artifact(output_path, name, contract_errors, technical_entries)
        if value is not None:
            artifacts[name] = value
    report: str | None = None
    report_path = output_path / "audit-report.md"
    if not report_path.exists():
        message = "Missing required human producer artifact: audit-report.md."
        _add_contract_error(contract_errors, message, "audit-report.md")
        technical_entries.append((_failure_record("report", "missing_artifact", message, "audit-report.md"), False))
    elif not report_path.is_file():
        message = "Malformed human producer artifact audit-report.md: expected a file."
        _add_contract_error(contract_errors, message, "audit-report.md")
        technical_entries.append((_failure_record("report", "malformed_artifact", message, "audit-report.md"), False))
    else:
        try:
            report = report_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            message = f"Malformed human producer artifact audit-report.md: {type(exc).__name__}."
            _add_contract_error(contract_errors, message, "audit-report.md")
            technical_entries.append((_failure_record("report", "malformed_artifact", message, "audit-report.md"), False))

    summary = artifacts.get("AUDIT_JSON_SUMMARY.json")
    case_mismatch = summary is not None and summary.get("case_id") not in (None, "", case_id)
    if case_mismatch:
        message = (
            "Producer case_id does not match requested case_id: "
            f"{summary.get('case_id')!r} != {case_id!r}."
        )
        _add_contract_error(contract_errors, message, "AUDIT_JSON_SUMMARY.json.case_id")
        technical_entries.append((_failure_record("producer", "case_id_mismatch", message, "AUDIT_JSON_SUMMARY.json"), False))
    if summary is not None and "findings" not in summary:
        message = "Malformed producer artifact AUDIT_JSON_SUMMARY.json: findings is required."
        _add_contract_error(contract_errors, message, "AUDIT_JSON_SUMMARY.json.findings")
        technical_entries.append((_failure_record("producer", "malformed_artifact", message, "AUDIT_JSON_SUMMARY.json"), False))
    coverage = artifacts.get("coverage.json")
    pipeline = artifacts.get("pipeline_summary.json")
    if summary is not None and not isinstance(summary.get("findings", []), list):
        message = "AUDIT_JSON_SUMMARY.json findings must be an array."
        _record_malformed_failure_entry(message, "AUDIT_JSON_SUMMARY.json.findings", contract_errors, technical_entries)
    findings_value = summary.get("findings", []) if summary is not None else []
    normalized_observations: list[dict[str, Any]] = []
    if isinstance(findings_value, list) and not case_mismatch:
        for index, finding in enumerate(findings_value):
            if not isinstance(finding, dict):
                _record_malformed_finding(index, "Finding must be an object.", contract_errors, technical_entries)
                continue
            try:
                normalized = _normalize_finding(finding, contract_errors, technical_entries, index)
                if normalized is not None:
                    _validate_candidate_observation(case_id, normalized)
                    normalized_observations.append(normalized)
            except (RecursionError, TypeError, ValueError, OverflowError) as exc:
                _record_malformed_finding(
                    index,
                    f"Finding is malformed and was dropped: {type(exc).__name__}.",
                    contract_errors,
                    technical_entries,
                )

    failure_artifacts: list[tuple[str, dict[str, Any] | None, bool]] = [] if case_mismatch else [
        ("AUDIT_JSON_SUMMARY.json", summary, True),
        ("coverage.json", coverage, False),
        ("pipeline_summary.json", pipeline, False),
    ]
    if not case_mismatch and summary is not None and isinstance(summary.get("audit_coverage"), dict):
        failure_artifacts.append(("AUDIT_JSON_SUMMARY.json", summary["audit_coverage"], True))

    def collect_failure_values(
        artifact_name: str,
        artifact: dict[str, Any],
        key: str,
        disclosed: bool,
        *,
        default_module: str = "producer",
        default_type: str = "failure",
    ) -> None:
        values = artifact.get(key, [])
        if values in (None, "", False):
            return
        base_path = f"{artifact_name}.{key}"
        if not isinstance(values, list):
            _record_malformed_failure_entry(
                f"{base_path} must be an array.", base_path, contract_errors, technical_entries
            )
            return
        for index, value in enumerate(values):
            entry_path = f"{base_path}[{index}]"
            try:
                parsed = _failure_from_value(
                    value,
                    artifact_name,
                    default_module=default_module,
                    default_type=default_type,
                    disclosed=disclosed,
                )
            except (RecursionError, TypeError, ValueError) as exc:
                parsed = None
                _record_malformed_failure_entry(
                    f"Malformed failure entry: {type(exc).__name__}.", entry_path, contract_errors, technical_entries
                )
            if parsed is not None:
                technical_entries.append(parsed)
            elif parsed is None and not any(
                entry.get("source") == entry_path for entry, _ in technical_entries
            ):
                _record_malformed_failure_entry(
                    "Failure entry must be a non-empty string or recognized object.",
                    entry_path,
                    contract_errors,
                    technical_entries,
                )

    for artifact_name, artifact, artifact_disclosed in failure_artifacts:
        if artifact is None:
            continue
        for key in _FAILURE_KEYS:
            collect_failure_values(artifact_name, artifact, key, artifact_disclosed)
        for key in ("detector_failures", "audit_coverage_gaps", "coverage_failures"):
            collect_failure_values(
                artifact_name,
                artifact,
                key,
                artifact_disclosed,
                default_type="audit_coverage_gap",
            )
        if artifact.get("audit_coverage_gap"):
            message = str(artifact.get("audit_coverage_gap_message", "Audit coverage gap disclosed by producer."))
            technical_entries.append(
                (_failure_record("audit.coverage", "audit_coverage_gap", message, artifact_name), artifact_disclosed)
            )
        workstreams = artifact.get("workstreams", [])
        if artifact_name == "pipeline_summary.json" and isinstance(workstreams, str):
            workstreams = []
        if isinstance(workstreams, list):
            for workstream_index, workstream in enumerate(workstreams):
                if not isinstance(workstream, dict):
                    _record_malformed_failure_entry(
                        "Workstream entry must be an object.",
                        f"{artifact_name}.workstreams[{workstream_index}]",
                        contract_errors,
                        technical_entries,
                    )
                    continue
                status = str(workstream.get("status", "")).lower()
                if status not in {"failed", "error", "timeout", "timed_out"}:
                    continue
                name = str(workstream.get("name", workstream.get("module", "workstream")))
                errors = workstream.get("errors", [])
                if isinstance(errors, list) and errors:
                    for error_index, error in enumerate(errors):
                        try:
                            parsed = _failure_from_value(
                                error,
                                artifact_name,
                                default_module=name,
                                default_type="workstream_failed",
                                disclosed=artifact_disclosed,
                            )
                        except (RecursionError, TypeError, ValueError) as exc:
                            parsed = None
                            _record_malformed_failure_entry(
                                f"Malformed failure entry: {type(exc).__name__}.",
                                f"{artifact_name}.workstreams[{workstream_index}].errors[{error_index}]",
                                contract_errors,
                                technical_entries,
                            )
                        if parsed is not None:
                            technical_entries.append(parsed)
                        elif parsed is None:
                            _record_malformed_failure_entry(
                                "Failure entry must be a non-empty string or recognized object.",
                                f"{artifact_name}.workstreams[{workstream_index}].errors[{error_index}]",
                                contract_errors,
                                technical_entries,
                            )
                elif errors in (None, "", False, []):
                    technical_entries.append(
                        (
                            _failure_record(name, "workstream_failed", f"Workstream status: {status}.", artifact_name, status=status),
                            artifact_disclosed,
                        )
                    )
                else:
                    _record_malformed_failure_entry(
                        "Workstream errors must be an array.",
                        f"{artifact_name}.workstreams[{workstream_index}].errors",
                        contract_errors,
                        technical_entries,
                    )
        elif workstreams not in (None, "", False, []):
            _record_malformed_failure_entry(
                f"{artifact_name}.workstreams must be an array.",
                f"{artifact_name}.workstreams",
                contract_errors,
                technical_entries,
            )

    observed_failures, disclosed_ids = _dedupe_failures(technical_entries)
    report_disclosed: set[tuple[Any, ...]] = set()
    if report and not case_mismatch:
        for record in observed_failures:
            if _report_discloses_failure(record, report):
                report_disclosed.add(_failure_identity(record))
    all_disclosed = disclosed_ids | report_disclosed
    reported_failures = [] if case_mismatch else [
        dict(record, reported=True)
        for record in observed_failures
        if _failure_identity(record) in all_disclosed
    ]

    package_discovered = package_path
    if package_discovered is None and pipeline is not None and not case_mismatch:
        candidate = pipeline.get("package", pipeline.get("package_root"))
        if isinstance(candidate, str):
            package_discovered = _file_uri_path(candidate)
            if package_discovered is None and candidate.startswith("/"):
                try:
                    package_discovered = Path(candidate.split("?", 1)[0].split("#", 1)[0]).absolute()
                except (OSError, RuntimeError, ValueError):
                    package_discovered = None
    roots = _redaction_roots(output_path, package_discovered, staging_paths, artifacts, report)
    try:
        boundary_violations = [] if case_mismatch else _boundary_violations(report, artifacts)
    except (RecursionError, TypeError, ValueError) as exc:
        message = f"Boundary scan failed: {type(exc).__name__}."
        _add_contract_error(contract_errors, message, "boundary_scanner")
        technical_entries.append((_failure_record("boundary_scanner", "execution_failure", message, "boundary_scanner"), False))
        observed_failures, disclosed_ids = _dedupe_failures(technical_entries)
        boundary_violations = []
    payload: dict[str, Any] = {
        "case_id": case_id,
        "observations": sorted(normalized_observations, key=_canonical),
        "technical_failures": observed_failures,
        "reported_technical_failures": sorted(reported_failures, key=_canonical),
        "boundary_violations": boundary_violations,
        "contract_errors": sorted(contract_errors, key=_canonical),
    }
    payload = _redact(payload, roots)

    observations = payload["observations"]
    assert isinstance(observations, list)
    used_ids: dict[str, int] = {}
    for observation in observations:
        base = "obs_" + hashlib.sha256(f"{case_id}|{_canonical(observation)}".encode("utf-8")).hexdigest()[:16]
        used_ids[base] = used_ids.get(base, 0) + 1
        observation["observation_id"] = base if used_ids[base] == 1 else f"{base}-{used_ids[base]}"
    observations.sort(key=lambda item: str(item["observation_id"]))

    validate_contract("observation.schema.json", payload)
    return payload
