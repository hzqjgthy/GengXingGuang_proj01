from datetime import datetime
from typing import Any, Dict


def build_report(case_data: Dict[str, Any], analysis: Dict[str, Any], review: Dict[str, Any]) -> Dict[str, Any]:
    if not review.get("confirmed"):
        raise ValueError("请先确认辨证与方剂结果")

    final_syndrome = review.get("primary_syndrome") or analysis["primary_syndrome"]
    final_principle = review.get("treatment_principle") or analysis["treatment_principle"]
    final_pathogenesis = review.get("pathogenesis") or analysis.get("pathogenesis", "")
    final_explanation = review.get("explanation") or analysis.get("explanation", "")
    final_formula = review.get("formula") or analysis["formula"]
    four = case_data.get("four_diagnosis") or {}
    tongue = four.get("tongue") or {}
    pulse = four.get("pulse") or {}
    symptoms = case_data.get("symptom_labels") or case_data.get("symptoms") or []
    now = datetime.now()

    medical_record = {
        "chief_complaint": case_data.get("chief_complaint", ""),
        "present_illness": case_data.get("present_illness", ""),
        "medical_history": case_data.get("medical_history", ""),
        "current_medications": case_data.get("current_medications", ""),
        "current_symptoms": "、".join(symptoms),
        "tongue": "、".join(str(value) for value in tongue.values() if value),
        "tongue_visual_analysis": analysis.get("tongue_analysis", {}).get("summary", ""),
        "pulse": "、".join(str(value) for value in pulse.values() if value),
        "tcm_diagnosis": final_syndrome,
        "pathogenesis": final_pathogenesis,
        "treatment_principle": final_principle,
        "formula": final_formula,
    }

    patient_report = {
        "summary": "%s，本次模拟分析提示以%s为主要倾向。" % (
            case_data.get("display_name", "演示患者"),
            final_syndrome,
        ),
        "explanation": final_explanation,
        "evidence": analysis.get("evidence", []),
        "lifestyle": analysis.get("lifestyle", []),
        "warnings": analysis.get("warnings", []),
        "tongue_analysis": analysis.get("tongue_analysis", {}),
        "disclaimer": "本报告由教学演示系统基于模拟数据生成，仅用于课程实践，不构成真实诊断、处方或用药建议。",
    }

    return {
        "demo_id": "DEMO-%s-%s" % (now.strftime("%Y%m%d%H%M"), case_data.get("code", "CASE")),
        "generated_at": now.strftime("%Y-%m-%d %H:%M"),
        "medical_record": medical_record,
        "patient_report": patient_report,
    }
