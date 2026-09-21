const STEPS = [
  { title: "信息采集", subtitle: "四诊与指标" },
  { title: "AI辨证", subtitle: "证候与依据" },
  { title: "方案确认", subtitle: "治法与方剂" },
  { title: "报告生成", subtitle: "病历与患者版" },
];

const SYMPTOMS = [
  { id: "thirst", label: "口干口渴", group: "津液" },
  { id: "strong_thirst", label: "口渴多饮", group: "津液" },
  { id: "cold_drinks", label: "喜冷饮", group: "津液" },
  { id: "dry_mouth", label: "咽干少津", group: "津液" },
  { id: "fatigue", label: "倦怠乏力", group: "全身" },
  { id: "short_breath", label: "气短懒言", group: "全身" },
  { id: "spontaneous_sweating", label: "自汗", group: "汗出" },
  { id: "night_sweat", label: "盗汗", group: "汗出" },
  { id: "excessive_hunger", label: "多食易饥", group: "饮食" },
  { id: "constipation", label: "大便干结", group: "二便" },
  { id: "nocturia", label: "夜尿频多", group: "二便" },
  { id: "cold_limbs", label: "畏寒肢冷", group: "寒热" },
  { id: "sore_waist", label: "腰膝酸软", group: "肢体" },
  { id: "edema", label: "下肢浮肿", group: "肢体" },
  { id: "numbness", label: "肢体麻木", group: "肢体" },
  { id: "blurred_vision", label: "视物模糊", group: "头面" },
  { id: "poor_sleep", label: "睡眠不佳", group: "睡眠" },
];

const state = {
  cases: [],
  caseData: null,
  config: null,
  currentStep: 0,
  maxStep: 0,
  analysisMode: "online",
  analysis: null,
  analysisMeta: null,
  review: null,
  report: null,
  reportTab: "medical",
  busy: false,
  error: null,
  uploadedImage: null,
};

document.addEventListener("DOMContentLoaded", init);

async function init() {
  bindGlobalEvents();
  try {
    const [config, casePayload] = await Promise.all([
      api("/api/config"),
      api("/api/cases"),
    ]);
    state.config = config;
    state.cases = casePayload.cases || [];
    updateModelStatus();
    if (!state.cases.length) {
      throw new Error("没有可用的演示病例");
    }
    await selectCase(state.cases[0].id);
  } catch (error) {
    renderFatal(error.message);
  }
}

function bindGlobalEvents() {
  document.querySelectorAll(".mode-button").forEach((button) => {
    button.addEventListener("click", () => {
      state.analysisMode = button.dataset.mode;
      document.querySelectorAll(".mode-button").forEach((item) => {
        item.classList.toggle("is-active", item.dataset.mode === state.analysisMode);
      });
      showToast(
        state.analysisMode === "online"
          ? "已选择在线模型；调用失败将直接报错"
          : "已选择预置演示数据模式"
      );
    });
  });

  document.getElementById("sidebar-reset").addEventListener("click", resetCase);
  document.getElementById("top-reset").addEventListener("click", resetCase);
}

async function api(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  let payload = {};
  try {
    payload = await response.json();
  } catch (_error) {
    // The status-based error below remains actionable when the body is not JSON.
  }
  if (!response.ok) {
    const details = payload.error?.details?.length
      ? `：${payload.error.details.join("、")}`
      : "";
    throw new Error(`${payload.error?.message || "请求失败"}${details}`);
  }
  return payload;
}

async function selectCase(caseId) {
  const payload = await api(`/api/cases/${encodeURIComponent(caseId)}`);
  state.caseData = payload.case;
  state.analysis = null;
  state.analysisMeta = null;
  state.review = null;
  state.report = null;
  state.reportTab = "medical";
  state.currentStep = 0;
  state.maxStep = 0;
  state.busy = false;
  state.error = null;
  state.uploadedImage = null;
  render();
}

async function resetCase() {
  if (!state.caseData) return;
  await selectCase(state.caseData.id);
  showToast("已恢复模拟病例的初始状态");
}

function render() {
  renderCaseList();
  renderWorkflow();
  updateHeader();

  if (!state.caseData) {
    renderFatal("病例加载失败");
    return;
  }

  if (state.currentStep === 0) renderCollection();
  if (state.currentStep === 1) renderAnalysis();
  if (state.currentStep === 2) renderReview();
  if (state.currentStep === 3) renderReport();
  refreshIcons();
}

function renderCaseList() {
  document.getElementById("case-count").textContent = state.cases.length;
  document.getElementById("case-list").innerHTML = state.cases
    .map(
      (item) => `
        <button class="case-card ${state.caseData?.id === item.id ? "is-active" : ""}"
          type="button" data-case-id="${escapeHtml(item.id)}" aria-label="选择${escapeHtml(item.display_name)}">
          <img class="case-thumb" src="${escapeHtml(item.image_url)}" alt="${escapeHtml(item.display_name)}模拟舌象">
          <span class="case-copy">
            <strong>${escapeHtml(item.display_name)}</strong>
            <span>${escapeHtml(item.expected_syndrome)}</span>
          </span>
          <i data-lucide="chevron-right"></i>
        </button>`
    )
    .join("");

  document.querySelectorAll("[data-case-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (button.dataset.caseId === state.caseData?.id) return;
      try {
        await selectCase(button.dataset.caseId);
        showToast(`已切换至${state.caseData.display_name}`);
      } catch (error) {
        showToast(error.message, true);
      }
    });
  });
}

function renderWorkflow() {
  document.getElementById("workflow-nav").innerHTML = STEPS.map((step, index) => {
    const complete = index < state.currentStep && index <= state.maxStep;
    const current = index === state.currentStep;
    return `
      <button class="workflow-step ${complete ? "is-complete" : ""} ${current ? "is-current" : ""}"
        type="button" data-step="${index}" ${index > state.maxStep ? "disabled" : ""}>
        <span class="step-number">${complete ? "✓" : String(index + 1).padStart(2, "0")}</span>
        <span><strong>${step.title}</strong><br><small>${step.subtitle}</small></span>
        <i data-lucide="chevron-right"></i>
      </button>`;
  }).join("");

  document.querySelectorAll("[data-step]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = Number(button.dataset.step);
      if (target <= state.maxStep) {
        state.currentStep = target;
        render();
      }
    });
  });
}

function updateHeader() {
  const step = STEPS[state.currentStep];
  document.getElementById("step-eyebrow").textContent = `STEP ${String(state.currentStep + 1).padStart(2, "0")}`;
  document.getElementById("page-title").textContent = step.title;
}

function updateModelStatus() {
  const label = document.getElementById("model-label");
  const dot = document.getElementById("model-dot");
  if (state.config?.online_configured) {
    label.textContent = `${providerLabel(state.config.provider)} · ${state.config.model}`;
    dot.classList.add("is-online");
  } else {
    label.textContent = "在线模型未配置";
    dot.classList.remove("is-online");
  }
}

function renderCollection() {
  const current = state.caseData;
  const bmi = calculateBmi(current.height_cm, current.weight_kg);
  const tongue = current.four_diagnosis.tongue;
  const pulse = current.four_diagnosis.pulse;
  const symptomIds = new Set(current.symptoms || []);
  const image = state.uploadedImage || current.image_url;

  document.getElementById("app-view").innerHTML = `
    <div class="page-heading">
      <div>
        <h2>采集本次模拟就诊信息</h2>
        <p>按临床顺序核对基础资料、症状、四诊和血糖指标。带星号字段用于启动辨证分析。</p>
      </div>
    </div>

    ${patientStrip(current, image)}

    <form id="intake-form" class="workspace-surface" novalidate>
      <section class="section-block">
        ${sectionTitle("01", "基本资料", "模拟患者人口学信息与糖尿病病程")}
        <div class="form-grid">
          ${inputField("patient-name", "姓名代号", current.display_name, "text", "span-4", true)}
          ${selectField("patient-sex", "性别", ["女", "男"], current.sex, "span-4", true)}
          ${inputField("patient-age", "年龄", current.age, "number", "span-4", true, "岁")}
          ${inputField("patient-height", "身高", current.height_cm, "number", "span-3", true, "cm")}
          ${inputField("patient-weight", "体重", current.weight_kg, "number", "span-3", true, "kg")}
          ${inputField("patient-bmi", "BMI", bmi, "text", "span-3", false, "kg/m²", true)}
          ${inputField("patient-course", "糖尿病病程", current.course_years, "number", "span-3", true, "年")}
        </div>
      </section>

      <section class="section-block">
        ${sectionTitle("02", "病史与问诊", "记录主要问题，并勾选与当前状态相关的症状")}
        <div class="form-grid">
          ${textAreaField("chief-complaint", "主诉", current.chief_complaint, "span-6", true)}
          ${textAreaField("present-illness", "现病史", current.present_illness, "span-6", true)}
          ${textAreaField("medical-history", "既往史", current.medical_history, "span-6")}
          ${textAreaField("current-medications", "当前用药", current.current_medications, "span-6")}
          <div class="field span-12">
            <span class="field-label required">症状选择</span>
            <div class="symptom-grid">
              ${SYMPTOMS.map((item) => `
                <label class="symptom-chip">
                  <input type="checkbox" name="symptom" value="${item.id}" ${symptomIds.has(item.id) ? "checked" : ""}>
                  <span>${escapeHtml(item.label)}</span>
                </label>`).join("")}
            </div>
          </div>
        </div>
      </section>

      <section class="section-block">
        ${sectionTitle("03", "四诊信息", "在线模式会将舌象图片与结构化四诊信息一并发送给千问视觉模型")}
        <div class="tongue-layout">
          <div>
            <div class="tongue-preview">
              <img id="tongue-preview-image" src="${escapeHtml(image)}" alt="当前模拟病例舌象">
              <span class="image-label">模拟舌象</span>
              <label class="upload-button">
                <i data-lucide="image-up"></i><span>替换图片</span>
                <input id="tongue-upload" type="file" accept="image/png,image/jpeg,image/webp">
              </label>
            </div>
          </div>
          <div class="form-grid">
            ${inputField("observation", "望诊摘要", current.four_diagnosis.observation, "text", "span-6")}
            ${inputField("listening-smelling", "闻诊摘要", current.four_diagnosis.listening_smelling, "text", "span-6")}
            ${selectField("tongue-color", "舌色", ["淡", "淡红", "红", "绛", "紫暗"], tongue.color, "span-3", true)}
            ${selectField("tongue-body", "舌形", ["正常", "偏瘦", "胖大", "边有齿痕"], tongue.body, "span-3")}
            ${selectField("tongue-coating", "苔色与苔质", ["薄白", "薄黄", "黄腻", "白润", "少苔", "剥苔"], tongue.coating, "span-3")}
            ${inputField("tongue-feature", "其他舌象", tongue.feature, "text", "span-3")}
            ${selectField("pulse-depth", "脉位", ["浮", "中取", "沉"], pulse.depth, "span-3")}
            ${selectField("pulse-rate", "脉率", ["迟", "平", "数"], pulse.rate, "span-3")}
            ${selectField("pulse-strength", "脉力", ["弱", "中等", "有力"], pulse.strength, "span-3")}
            ${selectField("pulse-quality", "综合脉象", ["细弱", "细数", "滑数", "弦", "沉细弱", "沉迟"], pulse.quality, "span-3", true)}
          </div>
        </div>
      </section>

      <section class="section-block">
        ${sectionTitle("04", "检验指标", "输入糖尿病相关指标，系统同步计算BMI并展示历史趋势")}
        <div class="form-grid">
          ${inputField("fasting-glucose", "空腹血糖", current.labs.fasting_glucose, "number", "span-4", true, "mmol/L", false, "0.1")}
          ${inputField("postprandial-glucose", "餐后2小时血糖", current.labs.postprandial_glucose, "number", "span-4", false, "mmol/L", false, "0.1")}
          ${inputField("hba1c", "糖化血红蛋白", current.labs.hba1c, "number", "span-4", false, "%", false, "0.1")}
          <div class="field span-12">
            ${renderTrendChart(current.history || [])}
          </div>
        </div>
      </section>

      <div class="action-bar">
        <div id="form-error" class="form-error"><i data-lucide="circle-alert"></i><span></span></div>
        <div class="action-group">
          <button class="button button-secondary" type="button" id="restore-case"><i data-lucide="rotate-ccw"></i>恢复病例</button>
          <button class="button button-primary" type="submit"><i data-lucide="sparkles"></i>保存并开始AI分析</button>
        </div>
      </div>
    </form>`;

  document.getElementById("intake-form").addEventListener("submit", handleAnalyze);
  document.getElementById("restore-case").addEventListener("click", resetCase);
  document.getElementById("patient-height").addEventListener("input", updateBmiField);
  document.getElementById("patient-weight").addEventListener("input", updateBmiField);
  document.getElementById("tongue-upload").addEventListener("change", handleImageUpload);
}

function patientStrip(current, image) {
  return `
    <div class="patient-strip accent-${escapeHtml(current.accent || "green")}">
      <div class="patient-image-wrap">
        <img src="${escapeHtml(image)}" alt="${escapeHtml(current.display_name)}模拟舌象">
        <span class="image-label">模拟</span>
      </div>
      <div class="patient-identity">
        <div class="patient-identity-top">
          <h3>${escapeHtml(current.display_name)}</h3>
          <span class="status-badge">${escapeHtml(current.expected_syndrome)}</span>
        </div>
        <div class="patient-meta">
          <span>${escapeHtml(current.sex)} · ${escapeHtml(current.age)}岁</span>
          <span>病程 ${escapeHtml(current.course_years)} 年</span>
          <span>病例 ${escapeHtml(current.code)}</span>
        </div>
        <p class="patient-headline">${escapeHtml(current.headline)}</p>
      </div>
      <div class="metric-cluster">
        ${miniMetric("空腹血糖", current.labs.fasting_glucose, "mmol/L")}
        ${miniMetric("餐后2h", current.labs.postprandial_glucose, "mmol/L")}
        ${miniMetric("HbA1c", current.labs.hba1c, "%")}
      </div>
    </div>`;
}

function sectionTitle(index, title, description) {
  return `
    <div class="section-title">
      <div class="title-copy">
        <span class="section-index">${index}</span>
        <div><h3>${escapeHtml(title)}</h3><p>${escapeHtml(description)}</p></div>
      </div>
    </div>`;
}

function inputField(id, label, value, type = "text", span = "", required = false, unit = "", readonly = false, step = "1") {
  return `
    <div class="field ${span}">
      <label for="${id}" class="${required ? "required" : ""}">${escapeHtml(label)}</label>
      <div class="${unit ? "input-with-unit" : ""}">
        <input class="input" id="${id}" type="${type}" value="${escapeHtml(value)}"
          ${required ? "required" : ""} ${readonly ? "readonly" : ""} ${type === "number" ? `step="${step}" min="0"` : ""}>
        ${unit ? `<span class="input-unit">${escapeHtml(unit)}</span>` : ""}
      </div>
    </div>`;
}

function selectField(id, label, options, selected, span = "", required = false) {
  return `
    <div class="field ${span}">
      <label for="${id}" class="${required ? "required" : ""}">${escapeHtml(label)}</label>
      <select class="select" id="${id}" ${required ? "required" : ""}>
        ${options.map((option) => `<option value="${escapeHtml(option)}" ${option === selected ? "selected" : ""}>${escapeHtml(option)}</option>`).join("")}
      </select>
    </div>`;
}

function textAreaField(id, label, value, span = "", required = false) {
  return `
    <div class="field ${span}">
      <label for="${id}" class="${required ? "required" : ""}">${escapeHtml(label)}</label>
      <textarea class="textarea" id="${id}" ${required ? "required" : ""}>${escapeHtml(value)}</textarea>
    </div>`;
}

function miniMetric(label, value, unit) {
  return `<div class="mini-metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}<small>${escapeHtml(unit)}</small></strong></div>`;
}

function renderTrendChart(history) {
  if (!history.length) return "";
  const values = history.map((item) => Number(item.fasting_glucose));
  const min = Math.min(...values) - 0.5;
  const max = Math.max(...values) + 0.5;
  const width = 520;
  const height = 82;
  const padX = 28;
  const padY = 12;
  const usableW = width - padX * 2;
  const usableH = height - padY * 2;
  const points = history.map((item, index) => {
    const x = padX + (usableW * index) / Math.max(1, history.length - 1);
    const y = padY + usableH - ((Number(item.fasting_glucose) - min) / Math.max(0.1, max - min)) * usableH;
    return { x, y, value: item.fasting_glucose, date: item.date.slice(5) };
  });
  return `
    <div class="chart-panel">
      <div class="chart-heading"><strong>空腹血糖趋势</strong><span>最近 ${history.length} 次模拟就诊</span></div>
      <svg class="trend-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="空腹血糖变化趋势">
        <line x1="${padX}" y1="${height - padY}" x2="${width - padX}" y2="${height - padY}" stroke="#d8dfdc" stroke-width="1" />
        <polyline points="${points.map((p) => `${p.x},${p.y}`).join(" ")}" fill="none" stroke="#356984" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />
        ${points.map((p) => `
          <circle cx="${p.x}" cy="${p.y}" r="4" fill="#ffffff" stroke="#356984" stroke-width="2" />
          <text x="${p.x}" y="${p.y - 9}" text-anchor="middle" font-size="9" fill="#356984">${escapeHtml(p.value)}</text>
          <text x="${p.x}" y="${height - 1}" text-anchor="middle" font-size="8" fill="#68756f">${escapeHtml(p.date)}</text>`).join("")}
      </svg>
    </div>`;
}

function handleImageUpload(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  if (!file.type.startsWith("image/") || file.size > 4 * 1024 * 1024) {
    showToast("请选择4MB以内的PNG、JPEG或WebP图片", true);
    event.target.value = "";
    return;
  }
  const reader = new FileReader();
  reader.addEventListener("load", () => {
    state.uploadedImage = reader.result;
    document.getElementById("tongue-preview-image").src = state.uploadedImage;
    showToast("已替换当前模拟舌象图片");
  });
  reader.readAsDataURL(file);
}

function updateBmiField() {
  const height = Number(document.getElementById("patient-height").value);
  const weight = Number(document.getElementById("patient-weight").value);
  document.getElementById("patient-bmi").value = calculateBmi(height, weight);
}

function calculateBmi(heightCm, weightKg) {
  const height = Number(heightCm) / 100;
  const weight = Number(weightKg);
  if (!height || !weight) return "--";
  return (weight / (height * height)).toFixed(1);
}

function collectCaseForm() {
  const selectedSymptoms = [...document.querySelectorAll('input[name="symptom"]:checked')].map((item) => item.value);
  const symptomLabels = selectedSymptoms.map((id) => SYMPTOMS.find((item) => item.id === id)?.label || id);
  return {
    ...deepClone(state.caseData),
    display_name: value("patient-name"),
    sex: value("patient-sex"),
    age: numberValue("patient-age"),
    height_cm: numberValue("patient-height"),
    weight_kg: numberValue("patient-weight"),
    bmi: calculateBmi(numberValue("patient-height"), numberValue("patient-weight")),
    course_years: numberValue("patient-course"),
    chief_complaint: value("chief-complaint"),
    present_illness: value("present-illness"),
    medical_history: value("medical-history"),
    current_medications: value("current-medications"),
    symptoms: selectedSymptoms,
    symptom_labels: symptomLabels,
    four_diagnosis: {
      observation: value("observation"),
      listening_smelling: value("listening-smelling"),
      tongue: {
        color: value("tongue-color"),
        body: value("tongue-body"),
        coating: value("tongue-coating"),
        feature: value("tongue-feature"),
      },
      pulse: {
        depth: value("pulse-depth"),
        rate: value("pulse-rate"),
        strength: value("pulse-strength"),
        quality: value("pulse-quality"),
      },
    },
    labs: {
      fasting_glucose: numberValue("fasting-glucose"),
      postprandial_glucose: numberValue("postprandial-glucose"),
      hba1c: numberValue("hba1c"),
    },
  };
}

async function handleAnalyze(event) {
  event.preventDefault();
  const form = event.currentTarget;
  if (!form.reportValidity()) return;

  const nextCase = collectCaseForm();
  const missing = [];
  if (!nextCase.symptoms.length) missing.push("至少选择一项症状");
  if (!Number.isFinite(nextCase.labs.fasting_glucose)) missing.push("空腹血糖");
  if (missing.length) {
    showFormError(`请补充：${missing.join("、")}`);
    return;
  }

  state.caseData = nextCase;
  state.analysis = null;
  state.analysisMeta = null;
  state.review = null;
  state.report = null;
  state.currentStep = 1;
  state.maxStep = Math.max(state.maxStep, 1);
  state.busy = true;
  state.error = null;
  render();

  try {
    const [payload] = await Promise.all([
      api("/api/analyze", {
        method: "POST",
        body: JSON.stringify({ case: caseForAnalysis(), mode: state.analysisMode }),
      }),
      delay(850),
    ]);
    applyAnalysisPayload(payload);
    state.busy = false;
    render();
  } catch (error) {
    state.busy = false;
    state.error = error.message;
    render();
  }
}

function renderAnalysis() {
  if (state.busy) {
    document.getElementById("app-view").innerHTML = `
      <div class="workspace-surface analysis-loading">
        <div class="scan-visual">
          <img src="${escapeHtml(state.uploadedImage || state.caseData.image_url)}" alt="正在分析模拟舌象">
          <span class="scan-line"></span><span class="scan-corners"></span>
        </div>
        <div class="loading-copy">
          <span class="eyebrow">AI ANALYSIS</span>
          <h2>正在整合四诊与检验信息</h2>
          <p>${state.analysisMode === "online"
            ? "正在调用千问多模态模型，联合分析舌象图片与结构化四诊数据。密钥、网络、限流或响应异常都会直接显示错误。"
            : "正在读取预置演示数据。该模式仅在用户主动选择后使用，不会由在线模式自动切换。"}</p>
          <div class="processing-list">
            ${processingItem("01", "校验四诊数据与核心指标")}
            ${processingItem("02", "匹配证候要素与中医知识")}
            ${processingItem("03", "生成可核验依据与调治建议")}
            ${processingItem("04", "检查结构并准备展示结果")}
          </div>
        </div>
      </div>`;
    return;
  }

  if (state.error || !state.analysis) {
    document.getElementById("app-view").innerHTML = `
      <div class="error-state">
        <i data-lucide="triangle-alert"></i>
        <h2>分析未完成</h2>
        <p>${escapeHtml(state.error || "暂无分析结果")}</p>
        <div class="action-group">
          <button id="back-to-form" class="button button-secondary" type="button">返回检查数据</button>
          <button id="retry-analysis" class="button button-primary" type="button">重试${state.analysisMode === "online" ? "在线模型" : "演示数据"}</button>
        </div>
      </div>`;
    document.getElementById("back-to-form").addEventListener("click", () => goToStep(0));
    document.getElementById("retry-analysis").addEventListener("click", retryCurrentAnalysis);
    return;
  }

  const result = state.analysis;
  const confidence = Math.round(Number(result.confidence) * 100);
  const modeLabel = state.analysisMeta?.mode === "online"
    ? `${providerLabel(state.analysisMeta.provider)} 在线模型`
    : "预置演示数据";

  document.getElementById("app-view").innerHTML = `
    <div class="page-heading">
      <div>
        <h2>辨证分析结果</h2>
        <p>结果基于当前模拟输入生成。页面展示的是可核验依据摘要，不包含模型内部思维过程。</p>
      </div>
    </div>
    <div class="result-layout">
      <article class="result-primary">
        <header class="diagnosis-hero">
          <div class="hero-label"><i data-lucide="sparkles"></i>主要候选证型</div>
          <div class="diagnosis-line">
            <h2>${escapeHtml(result.primary_syndrome)}</h2>
            <span class="confidence-copy">模型置信度 <strong>${confidence}%</strong></span>
          </div>
          <div class="confidence-track"><div class="confidence-fill" style="width:${confidence}%"></div></div>
          <div class="secondary-row">
            ${(result.secondary_syndromes || []).map((item) => `<span class="secondary-tag">次要候选：${escapeHtml(item.name)} · ${Math.round(Number(item.confidence) * 100)}%</span>`).join("")}
          </div>
        </header>
        <section class="result-section">
          <h3><i data-lucide="list-checks"></i>判断依据</h3>
          <ul class="evidence-list">${(result.evidence || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
        </section>
        ${renderTongueAnalysis(result.tongue_analysis)}
        <section class="result-section">
          <h3><i data-lucide="book-open-text"></i>中医解释</h3>
          <div class="theory-grid">
            <div class="theory-item"><span>病机概要</span><p>${escapeHtml(result.pathogenesis)}</p></div>
            <div class="theory-item"><span>调治原则</span><p>${escapeHtml(result.treatment_principle)}</p></div>
          </div>
        </section>
        <div class="action-bar">
          <button id="analysis-back" class="button button-secondary" type="button"><i data-lucide="arrow-left"></i>返回修改信息</button>
          <button id="analysis-next" class="button button-primary" type="button">进入方案确认<i data-lucide="arrow-right"></i></button>
        </div>
      </article>
      <aside class="result-aside">
        <div class="aside-image">
          <img src="${escapeHtml(state.uploadedImage || state.caseData.image_url)}" alt="${escapeHtml(state.caseData.display_name)}模拟舌象">
          <span class="engine-badge">${escapeHtml(modeLabel)}</span>
        </div>
        <div class="aside-content">
          <h3>本次输入摘要</h3>
          <dl class="summary-list">
            ${summaryRow("模拟患者", state.caseData.display_name)}
            ${summaryRow("主要症状", (state.caseData.symptom_labels || []).slice(0, 4).join("、"))}
            ${summaryRow("舌象", Object.values(state.caseData.four_diagnosis.tongue).join("、"))}
            ${summaryRow("脉象", Object.values(state.caseData.four_diagnosis.pulse).join("、"))}
            ${summaryRow("空腹血糖", `${state.caseData.labs.fasting_glucose} mmol/L`)}
          </dl>
          <div class="warning-stack">
            ${(result.warnings || []).map((item) => `<div class="warning-item"><i data-lucide="info"></i><span>${escapeHtml(item)}</span></div>`).join("")}
          </div>
        </div>
      </aside>
    </div>`;

  document.getElementById("analysis-back").addEventListener("click", () => goToStep(0));
  document.getElementById("analysis-next").addEventListener("click", () => {
    state.maxStep = Math.max(state.maxStep, 2);
    goToStep(2);
  });
}

function processingItem(index, text) {
  return `<div class="processing-item"><span>${index}</span><strong>${escapeHtml(text)}</strong></div>`;
}

function caseForAnalysis() {
  const payload = deepClone(state.caseData);
  if (state.uploadedImage) payload.tongue_image_data = state.uploadedImage;
  return payload;
}

function renderTongueAnalysis(tongueAnalysis) {
  if (!tongueAnalysis) return "";
  const features = Array.isArray(tongueAnalysis.features) ? tongueAnalysis.features : [];
  return `
    <section class="result-section tongue-analysis-section">
      <h3><i data-lucide="scan-eye"></i>舌象视觉分析</h3>
      <div class="tongue-analysis-grid">
        ${tongueObservation("图像质量", tongueAnalysis.image_quality)}
        ${tongueObservation("舌色", tongueAnalysis.tongue_color)}
        ${tongueObservation("舌形", tongueAnalysis.tongue_shape)}
        ${tongueObservation("苔色", tongueAnalysis.coating_color)}
        ${tongueObservation("苔质", tongueAnalysis.coating_texture)}
        ${tongueObservation("视觉特征", features.join("、") || "未见明显附加特征")}
      </div>
      <p class="tongue-summary">${escapeHtml(tongueAnalysis.summary || "")}</p>
    </section>`;
}

function tongueObservation(label, content) {
  return `<div class="tongue-observation"><span>${escapeHtml(label)}</span><strong>${escapeHtml(content || "未识别")}</strong></div>`;
}

function applyAnalysisPayload(payload) {
  state.analysis = payload.analysis;
  state.analysisMeta = payload.meta;
  state.review = {
    confirmed: false,
    primary_syndrome: payload.analysis.primary_syndrome,
    treatment_principle: payload.analysis.treatment_principle,
    pathogenesis: payload.analysis.pathogenesis,
    explanation: payload.analysis.explanation,
    formula: deepClone(payload.analysis.formula),
  };
}

async function retryCurrentAnalysis() {
  state.busy = true;
  state.error = null;
  render();
  try {
    const payload = await api("/api/analyze", {
      method: "POST",
      body: JSON.stringify({ case: caseForAnalysis(), mode: state.analysisMode }),
    });
    applyAnalysisPayload(payload);
    state.busy = false;
    render();
  } catch (error) {
    state.busy = false;
    state.error = error.message;
    render();
  }
}

function renderReview() {
  if (!state.analysis || !state.review) {
    goToStep(1);
    return;
  }
  const review = state.review;
  document.getElementById("app-view").innerHTML = `
    <div class="page-heading">
      <div>
        <h2>确认辨证与方剂建议</h2>
        <p>可编辑AI建议。报告只使用本页确认后的最终内容，所有药物与剂量均为教学示例。</p>
      </div>
    </div>
    <form id="review-form">
      <div class="review-layout">
        <section class="review-panel">
          <header class="review-panel-head"><h3>辨证结论</h3><span class="status-badge">可编辑</span></header>
          <div class="review-panel-body">
            <div class="form-grid">
              ${inputField("review-syndrome", "最终证型", review.primary_syndrome, "text", "span-6", true)}
              ${inputField("review-principle", "治法", review.treatment_principle, "text", "span-6", true)}
              ${textAreaField("review-pathogenesis", "病机说明", review.pathogenesis, "span-12", true)}
              ${textAreaField("review-explanation", "患者版通俗解释", review.explanation, "span-12", true)}
            </div>
            <div class="confirmation-box">
              <input id="review-confirm" type="checkbox" ${review.confirmed ? "checked" : ""}>
              <label for="review-confirm">
                <strong>我已核对本次教学演示结果</strong>
                <span>确认后才可生成病历和患者报告；该操作不代表真实临床签署。</span>
              </label>
            </div>
          </div>
        </section>
        <section class="review-panel">
          <header class="review-panel-head">
            <h3>方剂建议</h3>
            <button id="restore-ai" class="button button-secondary" type="button"><i data-lucide="undo-2"></i>恢复AI建议</button>
          </header>
          <div class="review-panel-body">
            <div class="field span-12">
              <label for="formula-name" class="required">方剂名称</label>
              <input class="input" id="formula-name" value="${escapeHtml(review.formula.name)}" required>
            </div>
            <div class="formula-table-wrap">
              <table class="formula-table">
                <thead><tr><th>药物</th><th>剂量</th><th>作用</th><th><span class="sr-only">操作</span></th></tr></thead>
                <tbody>
                  ${review.formula.items.map((item, index) => formulaRow(item, index)).join("")}
                </tbody>
              </table>
            </div>
            <button id="add-herb" class="button button-secondary inline-action" type="button"><i data-lucide="plus"></i>添加药物</button>
            <div class="field span-12" style="margin-top:15px">
              <label for="formula-notes">方剂说明</label>
              <textarea class="textarea" id="formula-notes">${escapeHtml(review.formula.notes || "")}</textarea>
            </div>
          </div>
        </section>
      </div>
      <div id="review-error" class="form-error" style="margin-top:14px"><i data-lucide="circle-alert"></i><span></span></div>
      <div class="action-bar" style="margin-top:14px;border:1px solid var(--line);border-radius:var(--radius)">
        <button id="review-back" class="button button-secondary" type="button"><i data-lucide="arrow-left"></i>返回分析结果</button>
        <button class="button button-accent" type="submit"><i data-lucide="file-check-2"></i>确认并生成报告</button>
      </div>
    </form>`;

  document.getElementById("review-form").addEventListener("submit", handleGenerateReport);
  document.getElementById("review-back").addEventListener("click", () => {
    saveReviewFromForm(false);
    goToStep(1);
  });
  document.getElementById("restore-ai").addEventListener("click", () => {
    state.review = {
      confirmed: false,
      primary_syndrome: state.analysis.primary_syndrome,
      treatment_principle: state.analysis.treatment_principle,
      pathogenesis: state.analysis.pathogenesis,
      explanation: state.analysis.explanation,
      formula: deepClone(state.analysis.formula),
    };
    render();
    showToast("已恢复AI原始建议");
  });
  document.getElementById("add-herb").addEventListener("click", () => {
    saveReviewFromForm(false);
    state.review.formula.items.push({ name: "", dose: "", purpose: "" });
    render();
  });
  document.querySelectorAll("[data-remove-herb]").forEach((button) => {
    button.addEventListener("click", () => {
      saveReviewFromForm(false);
      state.review.formula.items.splice(Number(button.dataset.removeHerb), 1);
      render();
    });
  });
}

function formulaRow(item, index) {
  return `
    <tr data-formula-row="${index}">
      <td><input class="input" data-herb-name value="${escapeHtml(item.name)}" aria-label="药物名称"></td>
      <td><input class="input" data-herb-dose value="${escapeHtml(item.dose)}" aria-label="药物剂量"></td>
      <td><input class="input" data-herb-purpose value="${escapeHtml(item.purpose)}" aria-label="药物作用"></td>
      <td><button class="table-icon-button" type="button" data-remove-herb="${index}" title="删除药物" aria-label="删除${escapeHtml(item.name || "该药物")}"><i data-lucide="trash-2"></i></button></td>
    </tr>`;
}

function saveReviewFromForm(requireConfirmation) {
  const rows = [...document.querySelectorAll("[data-formula-row]")];
  const items = rows.map((row) => ({
    name: row.querySelector("[data-herb-name]").value.trim(),
    dose: row.querySelector("[data-herb-dose]").value.trim(),
    purpose: row.querySelector("[data-herb-purpose]").value.trim(),
  })).filter((item) => item.name || item.dose || item.purpose);

  const confirmed = document.getElementById("review-confirm").checked;
  state.review = {
    confirmed,
    primary_syndrome: value("review-syndrome"),
    treatment_principle: value("review-principle"),
    pathogenesis: value("review-pathogenesis"),
    explanation: value("review-explanation"),
    formula: {
      name: value("formula-name"),
      items,
      notes: value("formula-notes"),
    },
  };

  if (requireConfirmation) {
    if (!confirmed) throw new Error("请勾选确认后再生成报告");
    if (!state.review.primary_syndrome || !state.review.treatment_principle || !state.review.formula.name) {
      throw new Error("请完整填写证型、治法和方剂名称");
    }
    if (!items.length || items.some((item) => !item.name || !item.dose)) {
      throw new Error("方剂至少包含一味名称和剂量完整的药物");
    }
  }
}

async function handleGenerateReport(event) {
  event.preventDefault();
  try {
    saveReviewFromForm(true);
  } catch (error) {
    showReviewError(error.message);
    return;
  }

  state.currentStep = 3;
  state.maxStep = 3;
  state.busy = true;
  state.error = null;
  render();
  try {
    const payload = await api("/api/report", {
      method: "POST",
      body: JSON.stringify({ case: state.caseData, analysis: state.analysis, review: state.review }),
    });
    state.report = payload.report;
    state.busy = false;
    render();
    showToast("病历与患者报告已生成");
  } catch (error) {
    state.busy = false;
    state.error = error.message;
    render();
  }
}

function renderReport() {
  if (state.busy) {
    document.getElementById("app-view").innerHTML = `
      <div class="empty-state"><i data-lucide="file-text"></i><h2>正在生成结构化报告</h2><p>系统正在同步最终证型、方剂与患者版解释。</p></div>`;
    return;
  }
  if (state.error || !state.report) {
    document.getElementById("app-view").innerHTML = `
      <div class="error-state"><i data-lucide="triangle-alert"></i><h2>报告生成失败</h2><p>${escapeHtml(state.error || "暂无报告")}</p><button id="report-back" class="button button-secondary" type="button">返回方案确认</button></div>`;
    document.getElementById("report-back").addEventListener("click", () => goToStep(2));
    return;
  }

  document.getElementById("app-view").innerHTML = `
    <div class="page-heading">
      <div><h2>报告已生成</h2><p>可在中医病历与患者版报告之间切换，并使用浏览器打印功能导出PDF。</p></div>
    </div>
    <div class="report-toolbar">
      <div class="report-tabs" role="tablist">
        <button class="report-tab ${state.reportTab === "medical" ? "is-active" : ""}" data-report-tab="medical" type="button">中医病历</button>
        <button class="report-tab ${state.reportTab === "patient" ? "is-active" : ""}" data-report-tab="patient" type="button">患者版报告</button>
      </div>
      <div class="action-group">
        <button id="report-edit" class="button button-secondary" type="button"><i data-lucide="pencil"></i>返回修改</button>
        <button id="report-print" class="button button-primary" type="button"><i data-lucide="printer"></i>打印 / 导出PDF</button>
      </div>
    </div>
    ${state.reportTab === "medical" ? renderMedicalReport() : renderPatientReport()}
    <div class="action-bar" style="margin-top:14px;border:1px solid var(--line);border-radius:var(--radius)">
      <span class="confidence-copy">演示编号 <strong style="font-size:14px">${escapeHtml(state.report.demo_id)}</strong></span>
      <button id="finish-reset" class="button button-accent" type="button"><i data-lucide="rotate-ccw"></i>完成并重置演示</button>
    </div>`;

  document.querySelectorAll("[data-report-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      state.reportTab = button.dataset.reportTab;
      render();
    });
  });
  document.getElementById("report-edit").addEventListener("click", () => goToStep(2));
  document.getElementById("report-print").addEventListener("click", () => window.print());
  document.getElementById("finish-reset").addEventListener("click", resetCase);
}

function renderMedicalReport() {
  const record = state.report.medical_record;
  return `
    <article class="report-paper" id="print-report">
      ${reportHeader("中医门诊病历（教学演示）")}
      ${reportMeta()}
      <section class="report-section">
        <h3>病情资料</h3>
        ${reportField("主诉", record.chief_complaint)}
        ${reportField("现病史", record.present_illness)}
        ${reportField("既往史", record.medical_history)}
        ${reportField("当前用药", record.current_medications)}
        ${reportField("刻下症", record.current_symptoms)}
        ${reportField("舌象", record.tongue)}
        ${reportField("视觉舌象分析", record.tongue_visual_analysis)}
        ${reportField("脉象", record.pulse)}
      </section>
      <section class="report-section">
        <h3>辨证与治法</h3>
        ${reportField("中医诊断", record.tcm_diagnosis)}
        ${reportField("病机", record.pathogenesis)}
        ${reportField("治法", record.treatment_principle)}
      </section>
      <section class="report-section">
        <h3>方剂建议</h3>
        <p><strong>${escapeHtml(record.formula.name)}</strong></p>
        ${renderReadonlyFormula(record.formula.items)}
        <div class="disclaimer-box">${escapeHtml(record.formula.notes || "本方仅为教学演示。")}</div>
      </section>
    </article>`;
}

function renderPatientReport() {
  const report = state.report.patient_report;
  return `
    <article class="report-paper" id="print-report">
      ${reportHeader("中医健康说明（患者版·教学演示）")}
      ${reportMeta()}
      <section class="report-section">
        <div class="patient-summary">${escapeHtml(report.summary)}</div>
      </section>
      <section class="report-section">
        <h3>结果说明</h3>
        <p>${escapeHtml(report.explanation)}</p>
      </section>
      <section class="report-section">
        <h3>本次判断参考</h3>
        <ul class="evidence-list">${(report.evidence || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
      </section>
      ${report.tongue_analysis ? `
        <section class="report-section">
          <h3>舌象图像观察</h3>
          <p>${escapeHtml(report.tongue_analysis.summary || "未生成舌象视觉分析")}</p>
        </section>` : ""}
      <section class="report-section">
        <h3>日常调护提示</h3>
        <div class="advice-grid">${(report.lifestyle || []).map((item) => `<div class="advice-item"><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.content)}</p></div>`).join("")}</div>
      </section>
      <div class="disclaimer-box">${escapeHtml(report.disclaimer)}</div>
    </article>`;
}

function reportHeader(title) {
  return `
    <header class="report-head">
      <div><h2>${escapeHtml(title)}</h2><p>糖医智辨 · 糖尿病中医智能辅助诊疗系统</p></div>
      <span class="report-mark">模拟数据</span>
    </header>`;
}

function reportMeta() {
  const patient = state.caseData;
  return `
    <div class="report-meta-grid">
      <div><span>姓名代号</span><strong>${escapeHtml(patient.display_name)}</strong></div>
      <div><span>性别 / 年龄</span><strong>${escapeHtml(patient.sex)} / ${escapeHtml(patient.age)}岁</strong></div>
      <div><span>糖尿病病程</span><strong>${escapeHtml(patient.course_years)}年</strong></div>
      <div><span>生成时间</span><strong>${escapeHtml(state.report.generated_at)}</strong></div>
    </div>`;
}

function reportField(label, content) {
  return `<div class="report-field"><span>${escapeHtml(label)}</span><p>${escapeHtml(content || "未记录")}</p></div>`;
}

function renderReadonlyFormula(items) {
  return `
    <table class="formula-table">
      <thead><tr><th>药物</th><th>剂量</th><th>作用说明</th></tr></thead>
      <tbody>${(items || []).map((item) => `<tr><td>${escapeHtml(item.name)}</td><td>${escapeHtml(item.dose)}</td><td>${escapeHtml(item.purpose)}</td></tr>`).join("")}</tbody>
    </table>`;
}

function summaryRow(label, valueText) {
  return `<div class="summary-row"><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(valueText || "未记录")}</dd></div>`;
}

function goToStep(step) {
  state.currentStep = step;
  render();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function showFormError(message) {
  const box = document.getElementById("form-error");
  box.querySelector("span").textContent = message;
  box.classList.add("is-visible");
  box.scrollIntoView({ behavior: "smooth", block: "center" });
}

function showReviewError(message) {
  const box = document.getElementById("review-error");
  box.querySelector("span").textContent = message;
  box.classList.add("is-visible");
  box.scrollIntoView({ behavior: "smooth", block: "center" });
}

function showToast(message, isError = false) {
  const toast = document.createElement("div");
  toast.className = `toast ${isError ? "is-error" : ""}`;
  toast.innerHTML = `<i data-lucide="${isError ? "triangle-alert" : "circle-check"}"></i><span>${escapeHtml(message)}</span>`;
  document.getElementById("toast-region").appendChild(toast);
  refreshIcons();
  window.setTimeout(() => toast.remove(), 3600);
}

function renderFatal(message) {
  document.getElementById("app-view").innerHTML = `
    <div class="error-state"><i data-lucide="server-off"></i><h2>Demo无法启动</h2><p>${escapeHtml(message)}</p><button class="button button-primary" type="button" onclick="window.location.reload()">重新加载</button></div>`;
  refreshIcons();
}

function refreshIcons() {
  if (window.lucide) window.lucide.createIcons({ attrs: { "aria-hidden": "true" } });
}

function providerLabel(provider) {
  if (provider === "deepseek") return "DeepSeek";
  if (provider === "qwen") return "千问";
  return "演示";
}

function value(id) {
  return document.getElementById(id)?.value.trim() || "";
}

function numberValue(id) {
  const raw = document.getElementById(id)?.value;
  return raw === "" || raw == null ? null : Number(raw);
}

function deepClone(valueToClone) {
  return JSON.parse(JSON.stringify(valueToClone));
}

function delay(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function escapeHtml(valueToEscape) {
  return String(valueToEscape ?? "").replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    '"': "&quot;",
  })[character]);
}
