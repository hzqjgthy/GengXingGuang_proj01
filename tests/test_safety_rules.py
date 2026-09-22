from services.safety_rules import check_formula


def test_formula_rule_detects_compatibility_conflict():
    result = check_formula({"items": [{"name": "甘草", "dose": "6g"}, {"name": "海藻", "dose": "10g"}]})
    assert result["passed"] is False
    assert any(alert["rule_id"] == "eighteen-anti" for alert in result["alerts"])


def test_formula_rule_detects_soft_dose_limit():
    result = check_formula({"items": [{"name": "黄芪", "dose": "45g"}]})
    assert result["passed"] is True
    assert any(alert["rule_id"] == "dose-upper-soft" for alert in result["alerts"])
