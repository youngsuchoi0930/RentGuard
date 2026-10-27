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
  const chart = page.getByRole("img", { name: "예상 주택가액 대비 근저당 50%, 보증금 68%" });
  await expect(chart).toBeVisible();
  const shares = await chart.evaluate((element) => ({
    mortgage: parseFloat((element.querySelector(".mortgage-segment") as HTMLElement).style.width),
    deposit: parseFloat((element.querySelector(".deposit-segment") as HTMLElement).style.width),
    marker: parseFloat((element as HTMLElement).style.getPropertyValue("--value-marker")),
  }));
  expect(shares.mortgage).toBeCloseTo(110 / 260 * 100, 2);
  expect(shares.deposit).toBeCloseTo(150 / 260 * 100, 2);
  expect(shares.marker).toBeCloseTo(220 / 260 * 100, 2);
  expect(analysisPayload).toMatchObject({
    mode: "precheck",
    deposit: 150_000_000,
    monthly_rent: 100_000,
    save_history: false,
    retention_days: 30,
  });
});

for (const scenario of [
  { name: "근저당 0원", mortgage: 0, deposit: 150_000_000, value: 470_000_000 },
  { name: "주택가액 100%", mortgage: 100_000_000, deposit: 150_000_000, value: 250_000_000 },
]) {
  test(`금액 그래프는 ${scenario.name}을 실제 비율로 표시한다`, async ({ page }) => {
    await page.route("**/api/v1/document-bundles/extract", route => route.fulfill({ json: documentBundle(false) }));
    await page.route("**/api/v1/analyses/from-extractions", route => {
      const result = analysisResult();
      result.facts.mortgage_amount = scenario.mortgage;
      result.facts.deposit = scenario.deposit;
      result.facts.estimated_value = scenario.value;
      return route.fulfill({ json: result });
    });
    await page.goto("/");
    await fillContractInputs(page);
    await uploadRequiredDocuments(page);
    await page.getByRole("button", { name: "문서에서 값 추출하기" }).click();
    await page.getByRole("button", { name: /확인한 값으로 위험 분석/ }).click();
    const chart = page.locator(".bar-track");
    await expect(chart).toBeVisible();
    const shares = await chart.evaluate((element) => ({
      mortgage: parseFloat((element.querySelector(".mortgage-segment") as HTMLElement).style.width),
      deposit: parseFloat((element.querySelector(".deposit-segment") as HTMLElement).style.width),
      marker: parseFloat((element as HTMLElement).style.getPropertyValue("--value-marker")),
    }));
    expect(shares.mortgage).toBeCloseTo(scenario.mortgage / scenario.value * 100, 2);
    expect(shares.deposit).toBeCloseTo(scenario.deposit / scenario.value * 100, 2);
    expect(shares.marker).toBe(100);
  });
}

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
