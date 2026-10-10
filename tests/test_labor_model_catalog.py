from pathlib import Path
from uuid import uuid4

import fitz
import pytest
from fastapi import HTTPException

from api.labor_models import (
    _company_has_limited_model_access,
    _ensure_model_access,
)
from services import labor_model_service


class FakeResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row


class FakeSession:
    def __init__(self, row):
        self.row = row

    def execute(self, *_args, **_kwargs):
        return FakeResult(self.row)

    def commit(self):
        pass


def test_catalog_contains_all_supplied_models_and_templates():
    expected_codes = {
        "TLG-INT-001", "TLG-RRL-002", "ATD-003", "CTTD-004", "CTE-005",
        "NEA-006", "CTT-007", "CTP-008", "PPCT-009", "CTI-010",
        "AAS-011", "AI-012",
    }

    assert set(labor_model_service.MODEL_CATALOG) == expected_codes
    for model in labor_model_service.MODEL_CATALOG.values():
        assert model["template_path"].startswith("Modelos Laborales/")
        assert (labor_model_service.ROOT / model["template_path"]).is_file()


def test_company_allowlist_restricts_models_and_allows_tlg_int_001(monkeypatch):
    monkeypatch.setenv("RESTRICTED_COMPANY_NAMES", "  Empresa Uno, HORMICRET SA ")

    restricted_user = {"organization_name": "empresa uno"}
    punctuation_variant = {"organization_name": "HORMICRET S.A."}
    unrestricted_user = {"organization_name": "Otra Empresa"}

    assert _company_has_limited_model_access(restricted_user)
    assert _company_has_limited_model_access(punctuation_variant)
    assert not _company_has_limited_model_access(unrestricted_user)
    _ensure_model_access(restricted_user, "TLG-INT-001")
    _ensure_model_access(unrestricted_user, "CTE-005")
    with pytest.raises(HTTPException) as error:
        _ensure_model_access(restricted_user, "CTE-005")
    assert error.value.status_code == 403
    assert error.value.detail["support_url"] == "/ui/#/soporte"


def test_renderer_fills_markers_in_all_templates(tmp_path, monkeypatch):
    monkeypatch.setattr(labor_model_service, "ALLOWED_STORAGE_DIR", tmp_path / "storage")

    for code, model in labor_model_service.MODEL_CATALOG.items():
        values = {
            field["key"]: ("2026-10-10" if field.get("input_type") == "date" else f"Dato {index}")
            for index, field in enumerate(model["fields"], start=1)
        }
        document_id = str(uuid4())
        row = {
            "id": document_id,
            "template_code": code,
            "template_path": model["template_path"],
            "fields": values,
            "employee_id": None,
            "status": "BORRADOR",
        }

        result = labor_model_service.render_instance(FakeSession(row), document_id, "test-org")
        with fitz.open(result["path"]) as rendered:
            text = "\n".join(page.get_text() for page in rendered)
            for field in model["fields"]:
                assert field["marker"] not in text, f"{code}: {field['marker']}"

        assert Path(result["path"]).is_file()


def test_renderer_resolves_legacy_root_template_path(tmp_path, monkeypatch):
    monkeypatch.setattr(labor_model_service, "ALLOWED_STORAGE_DIR", tmp_path / "storage")
    model = labor_model_service.MODEL_CATALOG["TLG-INT-001"]
    document_id = str(uuid4())
    fields = {field["key"]: f"Dato {index}" for index, field in enumerate(model["fields"], start=1)}
    row = {
        "id": document_id,
        "template_code": "TLG-INT-001",
        "template_path": Path(model["template_path"]).name,
        "fields": fields,
        "employee_id": None,
        "status": "BORRADOR",
    }

    result = labor_model_service.render_instance(FakeSession(row), document_id, "test-org")
    assert Path(result["path"]).is_file()