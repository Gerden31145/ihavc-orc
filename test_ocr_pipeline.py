import base64
from io import BytesIO

from fastapi.testclient import TestClient

import ocr_api


client = TestClient(ocr_api.app)


def _table_result(header, value):
    return {
        "tables_result": [
            {
                "body": [
                    {"row_start": 0, "row_end": 0, "col_start": 0, "col_end": 0, "words": header},
                    {"row_start": 1, "row_end": 1, "col_start": 0, "col_end": 0, "words": value},
                ]
            }
        ]
    }


def test_run_pipeline_with_ppstructure_regions(monkeypatch):
    monkeypatch.setattr(
        ocr_api,
        "extract_table_regions_with_ppstructure",
        lambda image: (
            [b"region-1", b"region-2"],
            {"enabled": True, "available": True, "region_count": 2, "fallback_reason": "", "error": None},
        ),
    )

    def fake_baidu(image_base64, token):
        marker = base64.b64decode(image_base64).decode("utf-8")
        return _table_result("院校", "A大学" if marker == "region-1" else "B大学")

    monkeypatch.setattr(ocr_api, "call_baidu_table_ocr", fake_baidu)

    matrix, raw, meta = ocr_api.run_table_recognition_pipeline(b"origin-image", "token")
    assert matrix[0] == ["院校"]
    assert matrix[1] == ["A大学"]
    assert matrix[2] == ["B大学"]
    assert len(raw["tables_result"]) == 2
    assert meta["pp_structure"]["fallback_used"] is False
    assert meta["pp_structure"]["region_count"] == 2


def test_run_pipeline_fallback_when_no_regions(monkeypatch):
    monkeypatch.setattr(
        ocr_api,
        "extract_table_regions_with_ppstructure",
        lambda image: (
            [],
            {
                "enabled": True,
                "available": True,
                "region_count": 0,
                "fallback_reason": "no_table_region_detected",
                "error": None,
            },
        ),
    )

    monkeypatch.setattr(ocr_api, "call_baidu_table_ocr", lambda image_base64, token: _table_result("院校", "整图结果"))
    matrix, _, meta = ocr_api.run_table_recognition_pipeline(b"origin-image", "token")

    assert matrix[0] == ["院校"]
    assert matrix[1] == ["整图结果"]
    assert meta["pp_structure"]["fallback_used"] is True


def test_run_pipeline_region_failed_then_full_image_fallback(monkeypatch):
    monkeypatch.setattr(
        ocr_api,
        "extract_table_regions_with_ppstructure",
        lambda image: (
            [b"bad-region"],
            {"enabled": True, "available": True, "region_count": 1, "fallback_reason": "", "error": None},
        ),
    )

    def fake_baidu(image_base64, token):
        marker = base64.b64decode(image_base64)
        if marker == b"bad-region":
            return {}
        return _table_result("院校", "兜底整图结果")

    monkeypatch.setattr(ocr_api, "call_baidu_table_ocr", fake_baidu)

    matrix, _, meta = ocr_api.run_table_recognition_pipeline(b"origin-image", "token")
    assert matrix[1] == ["兜底整图结果"]
    assert meta["pp_structure"]["fallback_used"] is True


def test_api_ocr_returns_legacy_fields_with_meta(monkeypatch):
    monkeypatch.setattr(ocr_api, "get_access_token", lambda: "token")
    monkeypatch.setattr(
        ocr_api,
        "run_table_recognition_pipeline",
        lambda image, token: (
            [["编号", "院校"], ["1", "A大学"]],
            {"tables_result": []},
            {"source_engine": "baidu_table_ocr", "pp_structure": {"enabled": True, "region_count": 1}},
        ),
    )

    response = client.post(
        "/api/ocr?enhance=false",
        files={"file": ("demo.png", BytesIO(b"img"), "image/png")},
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["data"]["headers"] == ["编号", "院校"]
    assert payload["data"]["rows"] == [["1", "A大学"]]
    assert payload["data"]["meta"]["source_engine"] == "baidu_table_ocr"
