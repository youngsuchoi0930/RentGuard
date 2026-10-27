import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { pdfFixtures } from "./fixtures";

async function fillReadyForm(page: Page) {
  await page.getByLabel("집 주소").fill("서울특별시 강서구 화곡로 123");
  await page.getByLabel("보증금").fill("150000000");
  const inputs = page.locator('input[type="file"]');
  await inputs.nth(0).setInputFiles(pdfFixtures.registry);
  await inputs.nth(1).setInputFiles(pdfFixtures.buildingLedger);
}

test("PDF가 아닌 파일을 즉시 거부한다", async ({ page }) => {
  await page.goto("/");
  await page.locator('input[type="file"]').first().setInputFiles({
    name: "not-a-pdf.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("not a pdf"),
  });

  await expect(page.locator(".error-banner")).toContainText(
    "현재 실제 분석은 PDF 파일만 지원합니다.",
  );
});

test("20MB를 넘는 PDF를 브라우저에서 거부한다", async ({ page }) => {
  await page.goto("/");
  await page.locator('input[type="file"]').first().setInputFiles({
    name: "oversized.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.alloc(20 * 1024 * 1024 + 1, 0),
  });

  await expect(page.locator(".error-banner")).toContainText(
    "파일은 문서당 20MB 이하만 업로드할 수 있습니다.",
  );
});

test("API 연결 실패를 사용자가 이해할 수 있게 안내한다", async ({ page }) => {
  await page.route("**/api/v1/document-bundles/extract", (route) => route.abort());
  await page.goto("/");
  await fillReadyForm(page);
  await page.getByRole("button", { name: "문서에서 값 추출하기" }).click();

  await expect(page.locator(".error-banner")).toContainText(
    "분석 API에 연결할 수 없습니다. API 서버가 실행 중인지 확인해주세요.",
  );
  await expect(
    page.getByRole("heading", { name: /계약하기 전/ }),
  ).toBeVisible();
});

test("핵심 입력은 키보드로 이동하고 분석 모드를 선택할 수 있다", async ({ page }) => {
  await page.goto("/");
  const precheck = page.getByRole("button", { name: /사전점검/ });
  const contractReview = page.getByRole("button", { name: /계약서 교차검증/ });

  await precheck.focus();
  await page.keyboard.press("Tab");
  await expect(contractReview).toBeFocused();
  await page.keyboard.press("Space");
  await expect(contractReview).toHaveAttribute("aria-pressed", "true");
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("집 주소")).toBeFocused();
});

test("초기 화면에 심각한 WCAG A/AA 위반이 없다", async ({ page }) => {
  await page.goto("/");
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const seriousViolations = results.violations.filter((violation) =>
    violation.impact === "serious" || violation.impact === "critical"
  );

  expect(seriousViolations).toEqual([]);
});

test("모바일 화면에 가로 스크롤이 생기지 않는다", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  const dimensions = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
  }));

  expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport);
  await expect(page.getByLabel("집 주소")).toBeVisible();
  await expect(page.getByRole("button", { name: /사전점검/ })).toBeVisible();
});

test("초기 화면과 분석 모드 전환에 브라우저 오류가 없다", async ({ page }) => {
  const browserErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") browserErrors.push(message.text());
  });
  page.on("pageerror", (error) => browserErrors.push(error.message));

  await page.goto("/");
  await page.getByRole("button", { name: /계약서 교차검증/ }).click();
  await page.getByRole("button", { name: /사전점검/ }).click();

  expect(browserErrors).toEqual([]);
});
