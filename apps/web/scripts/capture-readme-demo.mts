// Capture the actual UI with synthetic fixtures and mocked API responses only.
import { chromium, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { analysisResult, documentBundle, pdfFixtures } from "../e2e/fixtures.ts";

const baseURL = process.env.DEMO_BASE_URL ?? "http://127.0.0.1:3101";
const output = path.resolve(process.cwd(), "../../docs/screenshots");
await mkdir(output, { recursive: true });
const browser = await chromium.launch();
try {
  const landing = await browser.newPage({ viewport: { width: 2560, height: 1311 }, deviceScaleFactor: 1.5 });
  await landing.goto(baseURL);
  await landing.addStyleTag({ content: "nextjs-portal { display: none !important; }" });
  await expect(landing.locator(".profile strong")).toHaveText("user1");
  await landing.evaluate(() => document.fonts.ready);
  await landing.screenshot({ path: path.join(output, "home.png"), fullPage: true });
  const foregroundLayout = await landing.locator(".sidebar, .topbar, .page-heading, .form-card, .profile").evaluateAll(elements =>
    elements.map(element => element.getBoundingClientRect().toJSON()),
  );
  // Repaint the editable UI with only the page canvas removed. Browser rendering
  // retains Korean glyphs, card surfaces, shadows and exact foreground geometry.
  // The negative-z decorative underline is hidden by the original opaque canvas;
  // keep it hidden so removing that canvas does not reveal a new foreground item.
  await landing.addStyleTag({ content: "html, body { background: transparent !important; } .page-heading h1 em::after { visibility: hidden !important; }" });
  await expect(landing.locator("body")).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
  expect(await landing.locator(".sidebar, .topbar, .page-heading, .form-card, .profile").evaluateAll(elements =>
    elements.map(element => element.getBoundingClientRect().toJSON()),
  )).toEqual(foregroundLayout);
  await landing.screenshot({ path: path.join(output, "home-transparent.png"), fullPage: true, omitBackground: true });
  await landing.close();

  const page = await browser.newPage({ viewport: { width: 1440, height: 1080 }, deviceScaleFactor: 1 });
  await page.route("**/api/v1/document-bundles/extract", route => route.fulfill({ json: documentBundle(false) }));
  await page.route("**/api/v1/analyses/from-extractions", route => {
    const result = analysisResult();
    result.analysis_id = "SYNTHETIC-DEMO-001";
    result.summary = "합성 예시: 예상 집값 2.2억원 대비 근저당 한도와 보증금의 합은 약 118%입니다.";
    result.facts.local_price_volatility = 0;
    result.signals.push(
      { id: "mortgage", severity: "danger", title: "근저당 한도가 예상 집값의 50%예요", description: "채권최고액은 실제 대출 잔액과 다를 수 있어 잔액과 말소 계획을 확인하세요.", evidence: "1.1억원 / 2.2억원 = 50%", points: 20, sources: [] },
      { id: "deposit-ratio", severity: "danger", title: "보증금이 예상 집값의 약 68%예요", description: "가격 하락 시 보증금 회수 여력을 함께 확인하세요.", evidence: "1.5억원 / 2.2억원 ≈ 68%", points: 8, sources: [] },
    );
    result.score = 63;
    result.grade = "주의";
    result.ai_explanation.model = "synthetic-demo";
    result.ai_explanation.overview = "합성 화면 예시입니다. 근저당과 보증금을 함께 확인하는 흐름을 보여줍니다.";
    return route.fulfill({ json: result });
  });
  await page.goto(baseURL);
  await page.addStyleTag({ content: "nextjs-portal { display: none !important; } *, *::before, *::after { animation: none !important; transition: none !important; }" });
  await page.getByLabel("집 주소").fill("서울특별시 강서구 화곡로 123");
  await page.getByLabel("보증금", { exact: true }).fill("150000000");
  await page.getByLabel("월세", { exact: true }).fill("100000");
  const inputs = page.locator('input[type="file"]');
  await inputs.nth(0).setInputFiles(pdfFixtures.registry);
  await inputs.nth(1).setInputFiles(pdfFixtures.buildingLedger);
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: path.join(output, "input.png"), fullPage: true });
  await page.getByRole("button", { name: "문서에서 값 추출하기" }).click();
  await expect(page.getByRole("heading", { name: "분석 전에 추출값을 확인해주세요" })).toBeVisible();
  await page.screenshot({ path: path.join(output, "review.png"), fullPage: true });
  await page.getByRole("button", { name: /확인한 값으로 위험 분석/ }).click();
  await expect(page.locator(".result-stage")).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: path.join(output, "report.png"), fullPage: true });
  console.log(`Synthetic UI screenshots: ${output}`);
} finally {
  await browser.close();
}
