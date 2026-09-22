import copy


def test_home_and_health_are_available(client):
    home = client.get("/")
    health = client.get("/api/health")

    assert home.status_code == 200
    assert "糖医智辨" in home.get_data(as_text=True)
    assert health.status_code == 200
    assert health.get_json()["status"] == "ok"


def test_register_login_and_logout(client):
    registered = client.post("/api/auth/register", json={"username": "alice", "password": "secret123"})
    assert registered.status_code == 201
    assert registered.get_json()["user"]["username"] == "alice"

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.get_json()["user"]["username"] == "alice"

    logged_out = client.post("/api/auth/logout")
    assert logged_out.status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_history_is_saved_for_logged_in_user(client, case_a):
    client.post("/api/auth/register", json={"username": "history-user", "password": "secret123"})
    response = client.post("/api/analyze", json={"case": case_a, "mode": "demo"})
    assert response.status_code == 200
    saved = response.get_json()["saved"]
    assert saved["analysis_id"]

    history = client.get("/api/history")
    assert history.status_code == 200
    assert history.get_json()["history"][0]["primary_syndrome"] == "气阴两虚证"


def test_duplicate_username_is_rejected(client):
    assert client.post("/api/auth/register", json={"username": "duplicate", "password": "secret123"}).status_code == 201
    response = client.post("/api/auth/register", json={"username": "duplicate", "password": "secret123"})
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "REGISTER_INVALID"


def test_lists_three_demo_cases_without_full_medical_record(client):
    response = client.get("/api/cases")
    payload = response.get_json()

    assert response.status_code == 200
    assert len(payload["cases"]) == 3
    assert {item["id"] for item in payload["cases"]} == {"case-a", "case-b", "case-c"}
    assert all("present_illness" not in item for item in payload["cases"])


def test_case_detail_and_assets_are_available(client):
    response = client.get("/api/cases/case-b")
    case = response.get_json()["case"]
    image = client.get(case["image_url"])

    assert response.status_code == 200
    assert case["expected_syndrome"] == "阴虚热盛证"
    assert case["four_diagnosis"]["tongue"]["color"] == "红"
    assert image.status_code == 200
    assert image.content_type == "image/jpeg"


def test_missing_case_returns_structured_404(client):
    response = client.get("/api/cases/not-found")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "CASE_NOT_FOUND"


def test_all_demo_cases_reach_expected_primary_syndrome(client):
    expected = {
        "case-a": "气阴两虚证",
        "case-b": "阴虚热盛证",
        "case-c": "阴阳两虚证",
    }

    for case_id, syndrome in expected.items():
        case = client.get("/api/cases/%s" % case_id).get_json()["case"]
        response = client.post("/api/analyze", json={"case": case, "mode": "demo"})
        payload = response.get_json()

        assert response.status_code == 200
        assert payload["analysis"]["primary_syndrome"] == syndrome
        assert payload["meta"]["mode"] == "demo"
        assert payload["analysis"]["evidence"]
        assert payload["analysis"]["formula"]["items"]
        assert payload["analysis"]["tongue_analysis"]["summary"]


def test_edited_symptoms_change_demo_analysis(client, case_a):
    edited = copy.deepcopy(case_a)
    edited["symptoms"] = ["cold_limbs", "nocturia", "sore_waist", "edema"]
    edited["four_diagnosis"]["tongue"] = {
        "color": "淡",
        "body": "胖大",
        "coating": "白润",
        "feature": "边有齿痕",
    }
    edited["four_diagnosis"]["pulse"] = {
        "depth": "沉",
        "rate": "迟",
        "strength": "弱",
        "quality": "沉细弱",
    }

    response = client.post("/api/analyze", json={"case": edited, "mode": "demo"})

    assert response.status_code == 200
    assert response.get_json()["analysis"]["primary_syndrome"] == "阴阳两虚证"


def test_incomplete_case_returns_actionable_fields(client, case_a):
    incomplete = copy.deepcopy(case_a)
    incomplete["symptoms"] = []
    incomplete["four_diagnosis"]["tongue"]["color"] = ""
    incomplete["labs"]["fasting_glucose"] = None

    response = client.post("/api/analyze", json={"case": incomplete, "mode": "demo"})
    error = response.get_json()["error"]

    assert response.status_code == 400
    assert error["code"] == "INCOMPLETE_CASE"
    assert set(error["details"]) >= {"舌色", "空腹血糖", "至少一项症状"}


def test_online_mode_without_key_returns_error_and_no_demo_result(client, case_a):
    response = client.post("/api/analyze", json={"case": case_a, "mode": "online"})
    payload = response.get_json()

    assert response.status_code == 503
    assert payload["error"]["code"] == "ONLINE_MODEL_NOT_CONFIGURED"
    assert "analysis" not in payload


def test_report_requires_confirmation(client, case_a):
    analysis = client.post("/api/analyze", json={"case": case_a, "mode": "demo"}).get_json()["analysis"]
    response = client.post(
        "/api/report",
        json={"case": case_a, "analysis": analysis, "review": {"confirmed": False}},
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "REPORT_NOT_READY"


def test_report_uses_confirmed_edited_values(client, case_a):
    client.post("/api/auth/register", json={"username": "report-user", "password": "secret123"})
    analyzed = client.post("/api/analyze", json={"case": case_a, "mode": "demo"}).get_json()
    analysis = analyzed["analysis"]
    edited_formula = copy.deepcopy(analysis["formula"])
    edited_formula["name"] = "人工确认方（教学示例）"
    review = {
        "confirmed": True,
        "primary_syndrome": "人工确认：气阴两虚证",
        "treatment_principle": "人工确认：益气养阴",
        "pathogenesis": "人工修改后的病机说明。",
        "explanation": "人工修改后的患者版解释。",
        "formula": edited_formula,
    }

    response = client.post(
        "/api/report",
        json={"case": case_a, "analysis": analysis, "review": review, "analysis_id": analyzed["saved"]["analysis_id"]},
    )
    report = response.get_json()["report"]

    assert response.status_code == 200
    assert report["medical_record"]["tcm_diagnosis"] == review["primary_syndrome"]
    assert report["medical_record"]["pathogenesis"] == review["pathogenesis"]
    assert report["medical_record"]["formula"]["name"] == edited_formula["name"]
    assert report["patient_report"]["explanation"] == review["explanation"]
    assert "教学演示" in report["patient_report"]["disclaimer"]


def test_report_does_not_duplicate_saved_analysis(client, case_a):
    client.post("/api/auth/register", json={"username": "no-duplicate", "password": "secret123"})
    analyzed = client.post("/api/analyze", json={"case": case_a, "mode": "demo"}).get_json()
    review = {"confirmed": True, "primary_syndrome": analyzed["analysis"]["primary_syndrome"], "treatment_principle": analyzed["analysis"]["treatment_principle"], "pathogenesis": analyzed["analysis"]["pathogenesis"], "explanation": analyzed["analysis"]["explanation"], "formula": analyzed["analysis"]["formula"]}
    response = client.post("/api/report", json={"case": case_a, "analysis": analyzed["analysis"], "review": review, "analysis_id": analyzed["saved"]["analysis_id"]})
    assert response.status_code == 200
    assert len(client.get("/api/history").get_json()["history"]) == 1


def test_public_config_never_contains_api_key(client):
    response = client.get("/api/config")
    payload = response.get_json()

    assert response.status_code == 200
    assert "api_key" not in payload
    assert "LLM_API_KEY" not in response.get_data(as_text=True)
    assert payload["available_modes"] == ["online", "demo"]
