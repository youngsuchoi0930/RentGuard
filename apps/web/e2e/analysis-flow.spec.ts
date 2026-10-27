import { expect, test, type Page } from "@playwright/test";

import { analysisResult, documentBundle, pdfFixtures } from "./fixtures";

async function fillContractInputs(page: Page) {
  await page.getByLabel("집 주소").fill("서울특별시 강서구 화곡로 123");
  await page.getByLabel("보증금", { exact: true }).fill("150000000");
  await page.getByLabel("월세", { exact: true }).fill("100000");
}

async function uploadRequiredDocuments(page: Page, includeContract = false) {
  const inputs = page.locator('input[type="file"]');
  await inputs.nth(0).setInputFiles(pdfFixtures.registry);
  await inputs.nth(1).setInputFiles(pdfFixtures.buildingLedger);
  if (includeContract) {
    await inputs.nth(2).setInputFiles(pdfFixtures.leaseContract);
  }
}

test("사전점검 전체 흐름이 결과 리포트까지 이어진다", async ({ page }) => {
  let analysisPayload: Record<string, unknown> | null = null;
  await page.route("**/api/v1/document-bundles/extract", async (route) => {
    await route.fulfill({ json: documentBundle(false) });
  });
  await page.route("**/api/v1/analyses/from-extractions", async (route) => {
    analysisPayload = route.request().postDataJSON();
    await route.fulfill({ json: analysisResult() });
  });

  await page.goto("/");
  await expect(page.getByRole("button", { name: /사전점검/ })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await fillContractInputs(page);
  await uploadRequiredDocuments(page);
  await expect(page.getByText("2/2")).toBeVisible();

  await page.getByRole("button", { name: "문서에서 값 추출하기" }).click();
  await expect(
    page.getByRole("heading", { name: "분석 전에 추출값을 확인해주세요" }),
  ).toBeVisible();
  await page.getByRole("button", { name: /확인한 값으로 위험 분석/ }).click();

  await expect(
    page.getByRole("heading", { name: "확인 후 계약을 진행하세요" }),
  ).toBeVisible();
  await expect(page.getByText("73점")).toBeVisible();
  expect(analysisPayload).toMatchObject({
    mode: "precheck",
    deposit: 150_000_000,
    monthly_rent: 100_000,
    save_history: false,
    retention_days: 30,
  });
});

test("계약서 교차검증은 세 문서와 기록 보관 설정을 전달한다", async ({ page }) => {
  let analysisPayload: Record<string, unknown> | null = null;
  await page.route("**/api/v1/document-bundles/extract", async (route) => {
    await route.fulfill({ json: documentBundle(true) });
  });
  await page.route("**/api/v1/analyses/from-extractions", async (route) => {
    analysisPayload = route.request().postDataJSON();
    await route.fulfill({
      json: analysisResult({ includeContract: true, historySaved: true }),
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: /계약서 교차검증/ }).click();
  await fillContractInputs(page);
  await uploadRequiredDocuments(page, true);
  await expect(page.getByText("3/3")).toBeVisible();

  await page
    .getByRole("checkbox", { name: /개인정보를 제외한 분석 기록 저장/ })
    .check({ force: true });
  await page.getByLabel("자동 삭제 시점").selectOption("7");
  await page.getByRole("button", { name: "문서에서 값 추출하기" }).click();
  await expect(page.getByText("임대차계약서", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /확인한 값으로 위험 분석/ }).click();

  await expect(page.getByText(/계약서 교차검증 · 확인 필요한 항목 있음/)).toBeVisible();
  await expect(page.getByText("실제 서류와 결과가 맞나요?")).toBeVisible();
  expect(analysisPayload).toMatchObject({
    mode: "contract_review",
    save_history: true,
    retention_days: 7,
  });
});
