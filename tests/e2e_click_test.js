const fs = require("fs");
const { chromium } = require("playwright");

const APP_URL = process.env.APP_URL || "http://127.0.0.1:5001/";
const CHROME_PATH = process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

async function run() {
  const browser = await chromium.launch({ headless: true, executablePath: CHROME_PATH });
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  const report = { passed: [], failed: [], consoleErrors: [], expectedConsoleErrors: [], pageErrors: [], badResponses: [], expectedErrorResponses: [] };
  let expectAnalyzeError = false;
  const pass = (name, detail = "") => report.passed.push({ name, detail });
  const check = (condition, name, detail = "") => {
    if (!condition) throw new Error(`${name}${detail ? `: ${detail}` : ""}`);
    pass(name, detail);
  };

  page.on("console", (message) => {
    if (message.type() === "error") {
      if (expectAnalyzeError && message.text().includes("503")) report.expectedConsoleErrors.push(message.text());
      else report.consoleErrors.push(message.text());
    }
  });
  page.on("pageerror", (error) => report.pageErrors.push(error.message));
  page.on("response", (response) => {
    if (response.status() >= 400) {
      const item = { status: response.status(), url: response.url() };
      if (expectAnalyzeError && response.url().endsWith("/api/analyze")) report.expectedErrorResponses.push(item);
      else report.badResponses.push(item);
    }
  });

  try {
    await page.goto(APP_URL, { waitUntil: "networkidle" });
    await page.waitForSelector("#intake-form");
    check((await page.locator("[data-case-id]").count()) === 3, "三个病例卡片加载");
    check((await page.locator("#patient-name").inputValue()) === "演示患者 A", "默认载入病例A");
    check(await page.locator('[data-step="1"]').isDisabled(), "未分析时后续步骤禁用");

    await page.click('[data-case-id="case-b"]');
    await page.waitForFunction(() => document.querySelector("#patient-name")?.value === "演示患者 B");
    check((await page.locator("#fasting-glucose").inputValue()) === "9.4", "点击切换病例B", "空腹血糖9.4");
    await page.click('[data-case-id="case-c"]');
    await page.waitForFunction(() => document.querySelector("#patient-name")?.value === "演示患者 C");
    check((await page.locator("#tongue-color").inputValue()) === "淡", "点击切换病例C", "舌色为淡");
    await page.click('[data-case-id="case-a"]');
    await page.waitForFunction(() => document.querySelector("#patient-name")?.value === "演示患者 A");
    pass("病例A/B/C往返切换");

    await page.fill("#patient-height", "170");
    await page.fill("#patient-weight", "68");
    await page.locator("#patient-weight").dispatchEvent("input");
    check((await page.locator("#patient-bmi").inputValue()) === "23.5", "BMI自动计算", "170cm/68kg=23.5");
    await page.click("#restore-case");
    await page.waitForFunction(() => document.querySelector("#patient-height")?.value === "162");
    check((await page.locator("#patient-bmi").inputValue()) === "23.2", "表单内恢复病例");

    const symptoms = page.locator('input[name="symptom"]');
    for (let index = 0; index < await symptoms.count(); index += 1) {
      if (await symptoms.nth(index).isChecked()) await symptoms.nth(index).uncheck({ force: true });
    }
    await page.click('#intake-form button[type="submit"]');
    await page.waitForSelector("#form-error.is-visible");
    check((await page.locator("#form-error").textContent()).includes("至少选择一项症状"), "症状缺失校验拦截");
    await page.check('input[name="symptom"][value="thirst"]', { force: true });

    await page.setInputFiles("#tongue-upload", "static/images/tongue-case-b.jpg");
    await page.waitForFunction(() => document.querySelector("#tongue-preview-image")?.src.startsWith("data:image/"));
    check((await page.locator("#tongue-preview-image").getAttribute("src")).startsWith("data:image/"), "舌象图片替换与预览");

    await page.click("#top-reset");
    await page.waitForFunction(() => {
      const image = document.querySelector("#tongue-preview-image");
      return image && !image.getAttribute("src").startsWith("data:image/");
    });
    check(!(await page.locator("#tongue-preview-image").getAttribute("src")).startsWith("data:image/"), "顶部重置恢复原图");

    const onlineConfig = await page.request.get(`${APP_URL.replace(/\/$/, "")}/api/config`).then((response) => response.json());
    await page.click('[data-mode="online"]');
    if (onlineConfig.online_configured) {
      await page.click('#intake-form button[type="submit"]');
      await page.waitForSelector(".diagnosis-line h2", { timeout: 75000 });
      check((await page.locator(".engine-badge").textContent()).includes("在线模型"), "千问在线模型分析成功");
      check((await page.locator(".tongue-analysis-section").textContent()).includes("舌象视觉分析"), "千问返回舌象视觉分析");
      await page.click("#analysis-back");
      await page.waitForSelector("#intake-form");
    } else {
      expectAnalyzeError = true;
      await page.click('#intake-form button[type="submit"]');
      await page.waitForSelector(".error-state");
      expectAnalyzeError = false;
      check((await page.locator(".error-state").textContent()).includes("在线模型未配置"), "在线模型未配置时明确报错");
      check((await page.locator("#retry-analysis").textContent()).includes("在线模型"), "错误页只允许重试在线模型");
      check((await page.locator(".diagnosis-line").count()) === 0, "在线错误不生成演示分析结果");
      await page.click("#back-to-form");
      await page.waitForSelector("#intake-form");
    }

    await page.click('[data-mode="demo"]');
    await page.click('#intake-form button[type="submit"]');
    await page.waitForSelector(".diagnosis-line h2", { timeout: 12000 });
    check((await page.locator(".diagnosis-line h2").textContent()).trim() === "气阴两虚证", "主动选择演示数据后分析", "病例A=气阴两虚证");
    check((await page.locator(".engine-badge").textContent()).includes("预置演示数据"), "演示结果来源标识清晰");
    check((await page.locator(".tongue-analysis-section").textContent()).includes("舌象视觉分析"), "舌象分析结果区域显示");

    await page.click("#analysis-back");
    await page.waitForSelector("#intake-form");
    await page.fill("#chief-complaint", "修改后的演示主诉。");
    await page.click('#intake-form button[type="submit"]');
    await page.waitForSelector(".diagnosis-line h2", { timeout: 12000 });
    await page.click("#analysis-back");
    await page.waitForSelector("#intake-form");
    check((await page.locator("#chief-complaint").inputValue()) === "修改后的演示主诉。", "重新分析后保留已修改表单数据");

    await page.click('[data-step="1"]');
    await page.click("#analysis-next");
    await page.waitForSelector("#review-form");
    check((await page.locator("[data-formula-row]").count()) === 7, "方剂药物列表加载");

    await page.fill("#review-syndrome", "人工测试证型");
    await page.fill("#formula-name", "人工测试方（教学示例）");
    await page.click("#add-herb");
    check((await page.locator("[data-formula-row]").count()) === 8, "添加药物行");
    const lastRow = page.locator("[data-formula-row]").last();
    await lastRow.locator("[data-herb-name]").fill("测试药");
    await lastRow.locator("[data-herb-dose]").fill("1g");
    await lastRow.locator("[data-herb-purpose]").fill("交互测试");
    await lastRow.locator("[data-remove-herb]").click();
    check((await page.locator("[data-formula-row]").count()) === 7, "删除药物行");

    await page.click("#restore-ai");
    check((await page.locator("#review-syndrome").inputValue()) === "气阴两虚证", "恢复AI辨证建议");
    check((await page.locator("#formula-name").inputValue()).includes("生脉散合玉泉丸"), "恢复AI方剂建议");

    await page.click('#review-form button[type="submit"]');
    await page.waitForSelector("#review-error.is-visible");
    check((await page.locator("#review-error").textContent()).includes("勾选确认"), "未确认时阻止报告生成");

    await page.fill("#review-syndrome", "气阴两虚证（人工确认）");
    await page.fill("#review-explanation", "这是人工修改后的患者说明，用于验证报告同步。");
    await page.check("#review-confirm");
    await page.click('#review-form button[type="submit"]');
    await page.waitForSelector(".report-paper", { timeout: 10000 });
    check((await page.locator(".report-paper").textContent()).includes("气阴两虚证（人工确认）"), "人工确认结果同步到中医病历");

    await page.click('[data-report-tab="patient"]');
    await page.waitForFunction(() => document.querySelector(".report-head h2")?.textContent.includes("患者版"));
    check((await page.locator(".report-paper").textContent()).includes("这是人工修改后的患者说明"), "人工患者说明同步到患者报告");
    check((await page.locator(".report-paper").textContent()).includes("仅用于课程实践"), "患者报告免责声明");

    await page.evaluate(() => {
      window.__printCalled = false;
      window.print = () => { window.__printCalled = true; };
    });
    await page.click("#report-print");
    check(await page.evaluate(() => window.__printCalled), "打印/导出PDF按钮调用打印");
    await page.pdf({ path: "/tmp/tcm-click-test-report.pdf", format: "A4", printBackground: true });
    const pdfSize = fs.statSync("/tmp/tcm-click-test-report.pdf").size;
    check(pdfSize > 10000, "A4 PDF实际生成", `${pdfSize} bytes`);

    await page.click("#report-edit");
    await page.waitForSelector("#review-form");
    check(await page.locator("#review-confirm").isChecked(), "从报告返回修改保留确认状态");
    await page.click('#review-form button[type="submit"]');
    await page.waitForSelector(".report-paper");
    await page.click("#finish-reset");
    await page.waitForSelector("#intake-form");
    check((await page.locator("#chief-complaint").inputValue()) === "口干多饮伴乏力反复半年。", "完成并重置演示");
    check(await page.locator('[data-step="1"]').isDisabled(), "重置后流程状态归零");

    const expected = {
      "case-a": "气阴两虚证",
      "case-b": "阴虚热盛证",
      "case-c": "阴阳两虚证",
    };
    for (const [caseId, syndrome] of Object.entries(expected)) {
      await page.click(`[data-case-id="${caseId}"]`);
      await page.waitForSelector("#intake-form");
      await page.click('[data-mode="demo"]');
      await page.click('#intake-form button[type="submit"]');
      await page.waitForSelector(".diagnosis-line h2");
      const actual = (await page.locator(".diagnosis-line h2").textContent()).trim();
      check(actual === syndrome, `病例${caseId.slice(-1).toUpperCase()}完整辨证`, actual);
      await page.click("#analysis-back");
      await page.waitForSelector("#intake-form");
    }

    await page.click("#sidebar-reset");
    await page.waitForSelector("#intake-form");
    pass("侧栏重置按钮");
    check((await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)) === 0, "桌面页面无横向溢出");
    await page.screenshot({ path: "/tmp/tcm-click-test-final.png", fullPage: true });
  } catch (error) {
    report.failed.push({ name: "端到端点击测试", detail: error.stack || error.message });
    await page.screenshot({ path: "/tmp/tcm-click-test-failure.png", fullPage: true }).catch(() => {});
  }

  report.networkAndConsoleClean = report.consoleErrors.length === 0 && report.pageErrors.length === 0 && report.badResponses.length === 0;
  fs.writeFileSync("/tmp/tcm-click-test-results.json", JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
  await browser.close();
  if (report.failed.length || !report.networkAndConsoleClean) process.exit(1);
}

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
