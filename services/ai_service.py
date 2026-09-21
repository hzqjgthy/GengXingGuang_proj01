import base64
import copy
import json
import mimetypes
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests

from .case_store import CaseStore


PROVIDER_DEFAULTS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-vl-max",
    },
}


class AIServiceError(Exception):
    def __init__(self, code: str, message: str, status: int = 502):
        super().__init__(message)
        self.code = code
        self.status = status


class DemoAnalysisEngine:
    SYNDROME_RULES = {
        "qi_yin_deficiency": {
            "symptoms": {"thirst", "fatigue", "short_breath", "spontaneous_sweating", "dry_mouth"},
            "tongue": {"红", "少津", "裂纹"},
            "pulse": {"细", "弱", "虚"},
        },
        "yin_deficiency_heat": {
            "symptoms": {"strong_thirst", "cold_drinks", "excessive_hunger", "constipation", "night_sweat"},
            "tongue": {"红", "绛", "黄", "少苔"},
            "pulse": {"数", "细数", "滑数"},
        },
        "yin_yang_deficiency": {
            "symptoms": {"cold_limbs", "nocturia", "sore_waist", "fatigue", "edema"},
            "tongue": {"淡", "胖大", "齿痕", "白"},
            "pulse": {"沉", "弱", "迟", "细"},
        },
    }

    SYMPTOM_LABELS = {
        "thirst": "口干口渴",
        "fatigue": "倦怠乏力",
        "short_breath": "气短懒言",
        "spontaneous_sweating": "自汗",
        "dry_mouth": "咽干少津",
        "strong_thirst": "口渴多饮",
        "cold_drinks": "喜冷饮",
        "excessive_hunger": "多食易饥",
        "constipation": "大便干结",
        "night_sweat": "盗汗",
        "cold_limbs": "畏寒肢冷",
        "nocturia": "夜尿频多",
        "sore_waist": "腰膝酸软",
        "edema": "下肢浮肿",
        "blurred_vision": "视物模糊",
        "numbness": "肢体麻木",
        "poor_sleep": "睡眠不佳",
    }

    def __init__(self, store: CaseStore):
        self.store = store

    def analyze(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        scores = self._score_case(case_data)
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        primary_key, primary_score = ranked[0]
        result = self.store.get_result(primary_key)
        if result is None:
            raise RuntimeError("Missing demo result for %s" % primary_key)

        second_key, second_score = ranked[1]
        confidence = min(0.94, 0.78 + primary_score * 0.025 + max(0, primary_score - second_score) * 0.012)
        result["confidence"] = round(confidence, 2)
        result["secondary_syndromes"] = [
            {
                "name": self.store.get_result(second_key)["primary_syndrome"],
                "confidence": round(max(0.18, confidence - 0.24), 2),
            }
        ]
        evidence = self._build_evidence(case_data, primary_key)
        if evidence:
            result["evidence"] = evidence
        result["tongue_analysis"] = self._build_tongue_analysis(case_data)
        return result

    def _score_case(self, case_data: Dict[str, Any]) -> Dict[str, int]:
        selected = set(case_data.get("symptoms") or [])
        four = case_data.get("four_diagnosis") or {}
        tongue = four.get("tongue") or {}
        pulse = four.get("pulse") or {}
        tongue_text = " ".join(str(value) for value in tongue.values())
        pulse_text = " ".join(str(value) for value in pulse.values())

        scores: Dict[str, int] = {}
        for key, rule in self.SYNDROME_RULES.items():
            score = len(selected & rule["symptoms"]) * 2
            score += sum(1 for marker in rule["tongue"] if marker in tongue_text)
            score += sum(1 for marker in rule["pulse"] if marker in pulse_text)
            scores[key] = score

        if not any(scores.values()):
            expected = case_data.get("result_key")
            if expected in scores:
                scores[expected] = 4
            else:
                scores["qi_yin_deficiency"] = 1
        return scores

    def _build_evidence(self, case_data: Dict[str, Any], syndrome_key: str) -> List[str]:
        rule = self.SYNDROME_RULES[syndrome_key]
        selected = case_data.get("symptoms") or []
        evidence = [self.SYMPTOM_LABELS[item] for item in selected if item in rule["symptoms"]]
        four = case_data.get("four_diagnosis") or {}
        tongue = four.get("tongue") or {}
        pulse = four.get("pulse") or {}
        tongue_summary = "、".join(str(value) for value in tongue.values() if value)
        pulse_summary = "、".join(str(value) for value in pulse.values() if value)
        if tongue_summary:
            evidence.append("舌象：%s" % tongue_summary)
        if pulse_summary:
            evidence.append("脉象：%s" % pulse_summary)
        return evidence[:6]

    @staticmethod
    def _build_tongue_analysis(case_data: Dict[str, Any]) -> Dict[str, Any]:
        tongue = ((case_data.get("four_diagnosis") or {}).get("tongue") or {})
        return {
            "image_quality": "模拟舌象清晰，可用于界面演示",
            "tongue_color": tongue.get("color", "未记录"),
            "tongue_shape": tongue.get("body", "未记录"),
            "coating_color": tongue.get("coating", "未记录"),
            "coating_texture": tongue.get("coating", "未记录"),
            "features": [tongue.get("feature", "未见明显附加特征")],
            "summary": "演示数据模式沿用病例中预置的结构化舌象特征，未调用视觉模型。",
        }


class AIService:
    def __init__(self, store: CaseStore):
        self.store = store
        self.demo_engine = DemoAnalysisEngine(store)
        self.provider = os.getenv("LLM_PROVIDER", "deepseek").strip().lower()
        defaults = PROVIDER_DEFAULTS.get(self.provider, {})
        self.api_key = os.getenv("LLM_API_KEY", "").strip()
        self.base_url = os.getenv("LLM_BASE_URL", defaults.get("base_url", "")).strip().rstrip("/")
        self.model = os.getenv("LLM_MODEL", defaults.get("model", "")).strip()
        try:
            self.timeout = max(2.0, float(os.getenv("LLM_TIMEOUT_SECONDS", "10")))
        except ValueError:
            self.timeout = 10.0
        self.static_dir = Path(__file__).resolve().parents[1] / "static"

    @property
    def online_configured(self) -> bool:
        return (
            self.provider in PROVIDER_DEFAULTS
            and bool(self.api_key)
            and bool(self.base_url)
            and bool(self.model)
        )

    def public_config(self) -> Dict[str, Any]:
        return {
            "provider": self.provider if self.provider in PROVIDER_DEFAULTS else "demo",
            "model": self.model if self.online_configured else "确定性演示引擎",
            "online_configured": self.online_configured,
            "available_modes": ["online", "demo"],
        }

    def analyze(self, case_data: Dict[str, Any], mode: str = "online") -> Tuple[Dict[str, Any], Dict[str, Any]]:
        started = time.monotonic()
        selected_mode = mode if mode in {"online", "demo"} else "online"

        if selected_mode == "demo":
            result = self.demo_engine.analyze(case_data)
            return result, self._meta("demo", started)

        if not self.online_configured:
            raise AIServiceError(
                "ONLINE_MODEL_NOT_CONFIGURED",
                "在线模型未配置。请设置DeepSeek或千问的提供商、模型名称和API密钥。",
                503,
            )

        try:
            result = self._analyze_online(case_data)
        except Exception as exc:
            raise AIServiceError("ONLINE_MODEL_FAILED", self._friendly_error(exc), 502) from exc
        return result, self._meta("online", started)

    def _meta(self, mode: str, started: float) -> Dict[str, Any]:
        return {
            "mode": mode,
            "provider": self.provider if mode == "online" else "demo",
            "model": self.model if mode == "online" else "deterministic-demo-engine",
            "duration_ms": round((time.monotonic() - started) * 1000),
        }

    def _analyze_online(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        endpoint = self.base_url
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"

        model_case = self._prepare_case_for_model(case_data)
        image_data_url = self._resolve_tongue_image_data_url(case_data)
        user_content = [
            {
                "type": "text",
                "text": "请结合舌象图片与以下结构化模拟病例完成分析，只返回JSON：\n%s"
                % json.dumps(model_case, ensure_ascii=False),
            },
            {"type": "image_url", "image_url": {"url": image_data_url}},
        ]

        response = requests.post(
            endpoint,
            headers={
                "Authorization": "Bearer %s" % self.api_key,
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": user_content},
                ],
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        result = self._parse_json(content)
        self._validate_result(result)
        return result

    @staticmethod
    def _system_prompt() -> str:
        return """你是中医药人工智能教学Demo的多模态结构化分析模块。请先独立观察舌象图片，再结合结构化的症状、脉象、病史与血糖指标生成辅助辨证结果。图片观察必须与人工录入的舌象字段分开表达；如图片质量不足或两者冲突，要在warnings中明确说明。不得宣称确诊，不得保证疗效，不得建议停换现有药物。不要输出推理过程，只输出可核验的观察与输入依据。严格返回一个JSON对象，字段为：tongue_analysis对象，包含image_quality、tongue_color、tongue_shape、coating_color、coating_texture、features字符串数组、summary；primary_syndrome字符串；secondary_syndromes数组，每项含name和0到1的confidence；confidence为0到1；evidence字符串数组；pathogenesis字符串；treatment_principle字符串；formula对象，含name、items数组（每项含name、dose、purpose）及notes；explanation字符串；lifestyle数组，每项含title和content；warnings字符串数组。所有内容使用中文。"""

    @staticmethod
    def _prepare_case_for_model(case_data: Dict[str, Any]) -> Dict[str, Any]:
        allowed_fields = {
            "sex",
            "age",
            "height_cm",
            "weight_kg",
            "bmi",
            "course_years",
            "chief_complaint",
            "present_illness",
            "medical_history",
            "current_medications",
            "symptoms",
            "symptom_labels",
            "four_diagnosis",
            "labs",
        }
        return copy.deepcopy({key: value for key, value in case_data.items() if key in allowed_fields})

    def _resolve_tongue_image_data_url(self, case_data: Dict[str, Any]) -> str:
        uploaded = case_data.get("tongue_image_data")
        if isinstance(uploaded, str) and uploaded.startswith("data:image/") and ";base64," in uploaded:
            header, encoded = uploaded.split(",", 1)
            try:
                base64.b64decode(encoded, validate=True)
            except ValueError as exc:
                raise ValueError("上传的舌象图片Base64格式无效") from exc
            return "%s,%s" % (header, encoded)

        image_url = str(case_data.get("image_url", ""))
        prefix = "/static/"
        if not image_url.startswith(prefix):
            raise ValueError("未找到可供多模态模型分析的舌象图片")

        relative_path = Path(image_url[len(prefix) :])
        image_path = (self.static_dir / relative_path).resolve()
        static_root = self.static_dir.resolve()
        if static_root not in image_path.parents or not image_path.is_file():
            raise ValueError("舌象图片路径无效")
        mime_type = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        return "data:%s;base64,%s" % (mime_type, encoded)

    @staticmethod
    def _parse_json(content: str) -> Dict[str, Any]:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("在线模型未返回有效JSON")
        return json.loads(cleaned[start : end + 1])

    @staticmethod
    def _validate_result(result: Dict[str, Any]) -> None:
        required = {
            "primary_syndrome",
            "tongue_analysis",
            "secondary_syndromes",
            "confidence",
            "evidence",
            "pathogenesis",
            "treatment_principle",
            "formula",
            "explanation",
            "warnings",
        }
        missing = required - set(result)
        if missing:
            raise ValueError("在线模型结果缺少字段：%s" % ", ".join(sorted(missing)))
        if not isinstance(result["formula"], dict) or not isinstance(result["formula"].get("items"), list):
            raise ValueError("在线模型方剂结构无效")
        tongue_analysis = result["tongue_analysis"]
        required_tongue_fields = {
            "image_quality",
            "tongue_color",
            "tongue_shape",
            "coating_color",
            "coating_texture",
            "features",
            "summary",
        }
        if not isinstance(tongue_analysis, dict) or required_tongue_fields - set(tongue_analysis):
            raise ValueError("在线模型舌象分析结构无效")
        if not isinstance(tongue_analysis["features"], list):
            raise ValueError("在线模型舌象特征格式无效")
        result["confidence"] = max(0.0, min(1.0, float(result["confidence"])))
        result.setdefault("lifestyle", [])

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        if isinstance(exc, requests.Timeout):
            return "在线模型响应超时，请检查网络、模型状态或超时配置后重试。"
        if isinstance(exc, requests.HTTPError):
            status = exc.response.status_code if exc.response is not None else "未知"
            return "在线模型接口异常（HTTP %s），请检查密钥、额度、模型名称和接口地址。" % status
        if isinstance(exc, requests.RequestException):
            return "无法连接在线模型，请检查网络和接口地址后重试。"
        return "在线模型结果无效：%s" % str(exc)
