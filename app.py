import os
import secrets
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session

from services.ai_service import AIService, AIServiceError
from services.case_store import CaseStore
from services.db import Database, DatabaseError
from services.report_service import build_report


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def create_app(test_config: Dict[str, Any] = None) -> Flask:
    app = Flask(__name__)
    app.config.update(JSON_AS_ASCII=False, MAX_CONTENT_LENGTH=8 * 1024 * 1024, SECRET_KEY=os.getenv("APP_SECRET_KEY", secrets.token_hex(32)))
    if test_config:
        app.config.update(test_config)

    store = CaseStore(BASE_DIR / "data")
    ai_service = AIService(store)
    database = Database(BASE_DIR, test_config or {})
    app.extensions["case_store"] = store
    app.extensions["ai_service"] = ai_service
    app.extensions["database"] = database

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/health")
    def health():
        db_health = database.health()
        return jsonify({"status": "ok" if db_health["status"] == "ok" else "degraded", "service": "tcm-diabetes-demo", "database": db_health})

    @app.get("/api/config")
    def config():
        return jsonify(ai_service.public_config())

    @app.post("/api/auth/register")
    def register():
        payload = request.get_json(silent=True) or {}
        try:
            user = database.create_user(str(payload.get("username", "")), str(payload.get("password", "")))
        except ValueError as exc:
            return _error("REGISTER_INVALID", str(exc), 400)
        except DatabaseError as exc:
            return _error("DATABASE_ERROR", str(exc), 503)
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        return jsonify({"user": user}), 201

    @app.post("/api/auth/login")
    def login():
        payload = request.get_json(silent=True) or {}
        try:
            user = database.authenticate(str(payload.get("username", "")), str(payload.get("password", "")))
        except DatabaseError as exc:
            return _error("DATABASE_ERROR", str(exc), 503)
        if not user:
            return _error("LOGIN_FAILED", "用户名或密码不正确", 401)
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        return jsonify({"user": user})

    @app.post("/api/auth/logout")
    def logout():
        session.clear()
        return jsonify({"ok": True})

    @app.get("/api/auth/me")
    def me():
        if not session.get("user_id"):
            return _error("UNAUTHORIZED", "请先登录", 401)
        return jsonify({"user": {"id": session["user_id"], "username": session["username"]}})

    @app.get("/api/history")
    def history():
        user_id = _current_user_id()
        if not user_id:
            return _error("UNAUTHORIZED", "请先登录", 401)
        try:
            return jsonify({"history": database.list_history(user_id, request.args.get("limit", 50))})
        except DatabaseError as exc:
            return _error("DATABASE_ERROR", str(exc), 503)

    @app.get("/api/constitution/questions")
    def constitution_questions():
        return jsonify({"questions": ai_service.constitution_questions()})

    @app.post("/api/constitution/analyze")
    def constitution_analyze():
        user_id = _current_user_id()
        if not user_id:
            return _error("UNAUTHORIZED", "请先登录", 401)
        payload = request.get_json(silent=True) or {}
        answers = payload.get("answers")
        if not isinstance(answers, dict):
            return _error("INVALID_CONSTITUTION", "量表答案格式无效", 400)
        try:
            result = ai_service.analyze_constitution(answers)
            saved_id = database.save_constitution(user_id, answers, result["scores"], result["explanation"])
        except AIServiceError as exc:
            return _error(exc.code, str(exc), exc.status)
        except DatabaseError as exc:
            return _error("DATABASE_ERROR", str(exc), 503)
        return jsonify({"result": result, "saved_id": saved_id})

    @app.post("/api/knowledge-graph/generate")
    def knowledge_graph_generate():
        user_id = _current_user_id()
        if not user_id:
            return _error("UNAUTHORIZED", "请先登录", 401)
        payload = request.get_json(silent=True) or {}
        title = str(payload.get("title", "中医知识框图")).strip() or "中医知识框图"
        input_text = str(payload.get("input_text", "")).strip()
        if len(input_text) < 4:
            return _error("INVALID_GRAPH_INPUT", "请输入至少4个字符的知识主题或关系描述", 400)
        try:
            graph = ai_service.generate_knowledge_graph(input_text)
            saved_id = database.save_knowledge_graph(user_id, title, input_text, graph)
        except AIServiceError as exc:
            return _error(exc.code, str(exc), exc.status)
        except DatabaseError as exc:
            return _error("DATABASE_ERROR", str(exc), 503)
        return jsonify({"graph": graph, "saved_id": saved_id})

    @app.post("/api/inquiry")
    def inquiry():
        payload = request.get_json(silent=True) or {}
        case_data = payload.get("case") or {}
        symptoms = set(case_data.get("symptoms") or [])
        questions = []
        if "poor_sleep" not in symptoms:
            questions.append({"id": "sleep", "text": "最近一周睡眠情况如何？", "options": ["睡眠良好", "入睡困难", "容易醒", "多梦"]})
        if "constipation" not in symptoms and "nocturia" not in symptoms:
            questions.append({"id": "bowel", "text": "近期二便情况如何？", "options": ["基本正常", "大便干结", "大便偏稀", "夜尿增多"]})
        if "cold_limbs" not in symptoms and "strong_thirst" not in symptoms:
            questions.append({"id": "temperature", "text": "平时更容易怕冷还是怕热？", "options": ["无明显偏向", "怕冷", "怕热", "手足心热"]})
        return jsonify({"questions": questions[:5], "source": "rule-based-inquiry"})

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
        user_id = _current_user_id()
        saved = None
        if user_id:
            try:
                saved = database.save_analysis(user_id, case_data, result, meta)
            except DatabaseError as exc:
                return _error("DATABASE_ERROR", str(exc), 503)
        return jsonify({"analysis": result, "meta": meta, "saved": saved})

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
        user_id = _current_user_id()
        if user_id:
            try:
                analysis_id = payload.get("analysis_id")
                if analysis_id:
                    database.update_analysis_review(user_id, int(analysis_id), review)
                else:
                    database.save_analysis(user_id, case_data, analysis, {"provider": "report", "model": "reviewed"}, review)
            except DatabaseError as exc:
                return _error("DATABASE_ERROR", str(exc), 503)
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


def _current_user_id() -> int:
    try:
        return int(session.get("user_id")) if session.get("user_id") else 0
    except (TypeError, ValueError):
        return 0


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=False)
