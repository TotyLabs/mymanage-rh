from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services.legajo.ingestion import IngestionService


@pytest.mark.parametrize(
    ("canonical", "historical", "expected"),
    [
        ("101", "202", True),
        ("101", "101", False),
        ("101", None, False),
        (None, "202", False),
    ],
)
def test_legacy_legajo_conflicts_are_detected_without_overwriting_values(
    canonical, historical, expected
):
    service = IngestionService.__new__(IngestionService)
    service.db = MagicMock()
    employee = SimpleNamespace(file_number=canonical)
    service.db.query.return_value.outerjoin.return_value.filter.return_value.first.return_value = (
        employee,
        historical,
    )

    assert service._has_legacy_legajo_conflict("emp-1") is expected
    assert employee.file_number == canonical
    assert historical in (None, "101", "202")
