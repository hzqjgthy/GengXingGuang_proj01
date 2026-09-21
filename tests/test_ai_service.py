import base64
import json

import requests
import pytest

from services.ai_service import AIService, AIServiceError


def test_online_timeout_raises_error_without_demo_fallback(app, case_a, monkeypatch):
    service = AIService(app.extensions["case_store"])
    service.provider = "deepseek"
    service.api_key = "test-only-key"
    service.base_url = "https://example.invalid"
    service.model = "test-model"

    def timeout(_case_data):
        raise requests.Timeout("simulated timeout")

    monkeypatch.setattr(service, "_analyze_online", timeout)
    with pytest.raises(AIServiceError) as captured:
        service.analyze(case_a, mode="online")

    assert captured.value.code == "ONLINE_MODEL_FAILED"
    assert captured.value.status == 502
    assert "超时" in str(captured.value)


def test_unconfigured_online_mode_raises_configuration_error(app, case_a):
    service = AIService(app.extensions["case_store"])
    service.provider = "deepseek"
    service.api_key = ""
    service.model = "deepseek-chat"
    service.base_url = "https://api.deepseek.com"

    with pytest.raises(AIServiceError) as captured:
        service.analyze(case_a, mode="online")

    assert captured.value.code == "ONLINE_MODEL_NOT_CONFIGURED"
    assert captured.value.status == 503


def test_json_parser_accepts_fenced_response():
    parsed = AIService._parse_json('```json\n{"primary_syndrome":"气阴两虚证"}\n```')
    assert parsed["primary_syndrome"] == "气阴两虚证"


def test_model_input_removes_answer_and_internal_fields(app, case_a):
    service = AIService(app.extensions["case_store"])
    model_case = service._prepare_case_for_model(case_a)

    assert "expected_syndrome" not in model_case
    assert "result_key" not in model_case
    assert "id" not in model_case
    assert "image_url" not in model_case
    assert model_case["chief_complaint"] == case_a["chief_complaint"]


def test_default_tongue_image_is_encoded_as_data_url(app, case_a):
    service = AIService(app.extensions["case_store"])
    data_url = service._resolve_tongue_image_data_url(case_a)
    header, encoded = data_url.split(",", 1)

    assert header == "data:image/jpeg;base64"
    assert len(base64.b64decode(encoded)) > 1000


def test_qwen_request_contains_image_and_sanitized_case(app, case_a, monkeypatch):
    service = AIService(app.extensions["case_store"])
    service.provider = "qwen"
    service.api_key = "test-key"
    service.base_url = "https://example.invalid/v1"
    service.model = "qwen-vl-max"
    result = service.demo_engine.analyze(case_a)
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": json.dumps(result, ensure_ascii=False)}}]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr("services.ai_service.requests.post", fake_post)
    parsed = service._analyze_online(case_a)
    content = captured["json"]["messages"][1]["content"]
    text_part = next(item["text"] for item in content if item["type"] == "text")
    image_part = next(item["image_url"]["url"] for item in content if item["type"] == "image_url")

    assert parsed["tongue_analysis"]["summary"]
    assert "expected_syndrome" not in text_part
    assert "result_key" not in text_part
    assert image_part.startswith("data:image/jpeg;base64,")
