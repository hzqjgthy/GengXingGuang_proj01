import os
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from services.ai_service import AIService, AIServiceError
from services.case_store import CaseStore
from services.report_service import build_report


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def create_app(test_config: Dict[str, Any] = None) -> Flask:
    app = Flask(__name__)
    app.config.update(JSON_AS_ASCII=False, MAX_CONTENT_LENGTH=8 * 1024 * 1024)
    if test_config:
        app.config.update(test_config)

    store = CaseStore(BASE_DIR / "data")
    ai_service = AIService(store)
    app.extensions["case_store"] = store
    app.extensions["ai_service"] = ai_service

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "service": "tcm-diabetes-demo"})

    @app.get("/api/config")
    def config():
        return jsonify(ai_service.public_config())

    @app.get("/api/cases")
    def list_cases():
        return jsonify({"cases": store.list_cases()})

    @app.get("/api/cases/<case_id>")
    def get_case(case_id: str):
        case = store.get_case(case_id)
        if case is None:
            return _error("CASE_NOT_FOUND", "未找到该演示病例", 404)
        return jsonify({"case": case})

    @app.post("/api/analyze")
    def analyze():
        payload = request.get_json(silent=True) or {}
        case_data = payload.get("case")
        if not isinstance(case_data, dict):
            return _error("INVALID_CASE", "病例数据格式无效", 400)

        missing = _validate_case(case_data)
        if missing:
            return _error("INCOMPLETE_CASE", "请补充关键病例信息", 400, missing)

        try:
            result, meta = ai_service.analyze(case_data, payload.get("mode", "online"))
        except AIServiceError as exc:
            return _error(exc.code, str(exc), exc.status)
        return jsonify({"analysis": result, "meta": meta})

    @app.post("/api/report")
    def report():
        payload = request.get_json(silent=True) or {}
        case_data = payload.get("case")
        analysis = payload.get("analysis")
        review = payload.get("review")
        if not all(isinstance(item, dict) for item in (case_data, analysis, review)):
            return _error("INVALID_REPORT_DATA", "报告数据格式无效", 400)
        try:
            report_data = build_report(case_data, analysis, review)
        except (KeyError, ValueError) as exc:
            return _error("REPORT_NOT_READY", str(exc), 400)
        return jsonify({"report": report_data})

    @app.errorhandler(413)
    def payload_too_large(_error_object):
        return _error("PAYLOAD_TOO_LARGE", "分析请求超过8MB限制，请压缩舌象图片后重试", 413)

    @app.errorhandler(500)
    def internal_error(_error_object):
        return _error("INTERNAL_ERROR", "服务暂时不可用，请重试或重置演示", 500)

    return app


def _validate_case(case_data: Dict[str, Any]) -> List[str]:
    missing = []
    if not str(case_data.get("chief_complaint", "")).strip():
        missing.append("主诉")

    four = case_data.get("four_diagnosis") or {}
    tongue = four.get("tongue") or {}
    pulse = four.get("pulse") or {}
    if not tongue.get("color"):
        missing.append("舌色")
    if not pulse.get("quality"):
        missing.append("脉象")

    labs = case_data.get("labs") or {}
    if labs.get("fasting_glucose") in (None, ""):
        missing.append("空腹血糖")
    if not case_data.get("symptoms"):
        missing.append("至少一项症状")
    return missing


def _error(code: str, message: str, status: int, details: List[str] = None):
    payload: Dict[str, Any] = {"error": {"code": code, "message": message}}
    if details:
        payload["error"]["details"] = details
    return jsonify(payload), status


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=False)
