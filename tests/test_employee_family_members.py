import json

from services.family_members import normalize_family_members_payload


def test_normalize_family_members_payload_accepts_json_string():
    payload = json.dumps([
        {
            "vinculo": "Cónyuge",
            "nombre": "Ana Perez",
            "cuil": "27123456789",
            "fecha_nacimiento": "1990-01-01",
        }
    ])

    result = normalize_family_members_payload(payload)

    assert len(result) == 1
    assert result[0]["vinculo"] == "Cónyuge"
    assert result[0]["nombre"] == "Ana Perez"


def test_normalize_family_members_payload_rejects_empty_values():
    payload = json.dumps([{"vinculo": "", "nombre": "", "cuil": ""}])

    assert normalize_family_members_payload(payload) == []
