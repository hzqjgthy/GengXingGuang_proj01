from typing import Any, Dict, List


FORMULA_RULES = [
    {"id": "dose-upper-soft", "type": "dose", "name": "教学剂量软上限", "max_grams": 30, "message": "单味药物剂量超过30g，建议人工复核。"},
    {"id": "eighteen-anti", "type": "compatibility", "name": "十八反提示", "pairs": [("甘草", "海藻"), ("乌头", "贝母"), ("乌头", "瓜蒌"), ("乌头", "半夏"), ("乌头", "白蔹"), ("乌头", "白及")], "message": "检测到可能的十八反配伍组合。"},
    {"id": "nineteen-fear", "type": "compatibility", "name": "十九畏提示", "pairs": [("人参", "五灵脂"), ("官桂", "赤石脂"), ("丁香", "郁金"), ("巴豆", "牵牛")], "message": "检测到可能的十九畏配伍组合。"},
]


def check_formula(formula: Dict[str, Any]) -> Dict[str, Any]:
    items = formula.get("items") or []
    names = [str(item.get("name", "")).strip() for item in items if item.get("name")]
    alerts: List[Dict[str, Any]] = []
    for item in items:
        raw_dose = str(item.get("dose", ""))
        number = "".join(ch for ch in raw_dose if ch.isdigit() or ch == ".")
        if number:
            try:
                if float(number) > 30:
                    alerts.append({"rule_id": "dose-upper-soft", "level": "warning", "name": "教学剂量软上限", "message": "药物%s的剂量为%s，超过30g软上限。" % (item.get("name", "未命名"), raw_dose)})
            except ValueError:
                pass
    for rule in FORMULA_RULES[1:]:
        for left, right in rule["pairs"]:
            if left in names and right in names:
                alerts.append({"rule_id": rule["id"], "level": "danger", "name": rule["name"], "message": rule["message"] + "组合：%s + %s。" % (left, right)})
    return {"passed": not any(item["level"] == "danger" for item in alerts), "alerts": alerts, "rule_version": "demo-rules-1"}
