import json
from typing import Any, Iterable


def normalize_family_members_payload(raw_value: Any):
    if raw_value is None or raw_value == "":
        return []

    if isinstance(raw_value, str):
        raw_value = raw_value.strip()
        if not raw_value or raw_value.lower() in {"null", "none", "[]"}:
            return []
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            items = parsed
        elif isinstance(parsed, dict):
            items = [parsed]
        else:
            return []
    elif isinstance(raw_value, dict):
        items = [raw_value]
    elif isinstance(raw_value, list):
        items = raw_value
    else:
        return []

    normalized = []
    for item in items:
        if not isinstance(item, dict):
            continue

        cleaned = {}
        for field in (
            "vinculo",
            "nombre",
            "cuil",
            "documento",
            "documentacion",
            "fecha_nacimiento",
            "acta",
            "nivel_escolar",
            "t",
            "f",
        ):
            value = item.get(field)
            if value is None:
                continue
            text_value = str(value).strip()
            if text_value:
                cleaned[field] = text_value

        if not cleaned:
            continue

        if not any(cleaned.get(field) for field in ("vinculo", "nombre", "cuil", "documento", "fecha_nacimiento", "documentacion", "acta", "nivel_escolar", "t", "f")):
            continue

        normalized.append(cleaned)

    return normalized
