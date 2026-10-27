import path from "node:path";

export const pdfFixtures = {
  registry: path.resolve(
    process.cwd(),
    "../../output/pdf/rentguard-fixtures/registry_risky_digital.pdf",
  ),
  buildingLedger: path.resolve(
    process.cwd(),
    "../../output/pdf/rentguard-fixtures/building_ledger_risky.pdf",
  ),
  leaseContract: path.resolve(
    process.cwd(),
    "../../output/pdf/rentguard-fixtures/lease_contract_risky.pdf",
  ),
};

const evidence = {
  page: 1,
  section: "합성 테스트",
  raw_text: "합성 테스트 원문",
  extraction_method: "pdf_text",
  confidence: 0.99,
};

const registry = {
  property: {
    road_address: "서울특별시 강서구 화곡로 123",
    lot_address: "서울특별시 강서구 화곡동 1",
    building_name: "테스트빌라",
    unit: "201호",
  },
  evidence: { road_address: evidence },
  ownership: [
    {
      owner_name: "김민준",
      role: "owner",
      status: "active",
      evidence,
    },
  ],
  encumbrances: [
    {
      right_type: "mortgage",
      maximum_claim_amount: 110_000_000,
      status: "active",
      evidence,
    },
  ],
  confidence: 0.99,
  needs_review: [],
};

const buildingLedger = {
  property: {
    road_address: "서울특별시 강서구 화곡로 123",
    lot_address: "서울특별시 강서구 화곡동 1",
    building_name: "테스트빌라",
    unit: "201호",
    floor: 2,
    exclusive_area: 84.59,
    main_use: "다세대주택",
    structure: "철근콘크리트",
    households: 8,
    approval_date: "2017-06-20",
    is_illegal_building: false,
  },
  evidence: {
    road_address: evidence,
    unit: evidence,
    exclusive_area: evidence,
    main_use: evidence,
    approval_date: evidence,
    is_illegal_building: evidence,
  },
  confidence: 0.98,
  needs_review: [],
};

const leaseContract = {
  property: {
    address: "서울특별시 강서구 화곡로 123, 201호",
    building_description: "테스트빌라",
    leased_part: "201호",
  },
  evidence: { address: evidence },
  parties: [
    { role: "landlord", name: "김민준", evidence },
    { role: "tenant", name: "이서연", evidence },
  ],
  deposit: { value: 150_000_000, evidence },
  monthly_rent: { value: 100_000, evidence },
  confidence: 0.97,
  needs_review: [],
};

export function documentBundle(includeContract = false) {
  return {
    registry,
    building_ledger: buildingLedger,
    lease_contract: includeContract ? leaseContract : null,
    cross_checks: [],
  };
}

export function analysisResult(options?: {
  includeContract?: boolean;
  historySaved?: boolean;
}) {
  const includeContract = options?.includeContract ?? false;
  return {
    analysis_id: "E2E0BEEF12345678",
    mode: includeContract ? "contract_review" : "precheck",
    status: "needs_review",
    score: 73,
    grade: "높음",
    headline: "확인 후 계약을 진행하세요",
    summary: "근저당과 보증금을 합친 부담을 확인했습니다.",
    facts: {
      owner: "김민준",
      contract_owner: includeContract ? "김민준" : null,
      mortgage_amount: 110_000_000,
      deposit: 150_000_000,
      monthly_rent: 100_000,
      estimated_value: 220_000_000,
      estimated_value_low: 200_000_000,
      estimated_value_high: 240_000_000,
      building_use: "다세대주택",
      is_illegal_building: false,
      approval_year: 2017,
      recent_transactions: 32,
      local_price_volatility: 8,
    },
    signals: [
      {
        id: "senior-burden",
        severity: "danger",
        title: "선순위 부담 비율이 높아요",
        description: "보증금 회수 여력을 최신 등기부와 함께 확인해야 합니다.",
        evidence: "예상 부담 비율 118%",
        points: 35,
        sources: [],
      },
    ],
    checks: [
      {
        label: "등기 소유자 확인",
        status: "verified",
        detail: "현재 소유자를 확인했습니다.",
        sources: [],
        comparisons: [],
        next_step: null,
      },
    ],
    actions: [
      "잔금 지급 직전 최신 등기부등본을 다시 확인하세요.",
      "보증기관에 가입 가능 여부를 확인하세요.",
    ],
    market_data: {
      status: "available",
      message: "비교 거래를 확인했습니다.",
      source: "국토교통부",
      method: "유사 전용면적 거래 중간가격",
      as_of: "2026-10-01",
    },
    deposit_market: {
      status: "available",
      message: "입력 보증금이 예측 시장 범위 안에 있습니다.",
      expected_deposit: 140_000_000,
      upper_deposit: 180_000_000,
      upper_ratio: 0.83,
      exceeds_upper: false,
      source: "국토교통부 전월세 신고자료",
      model_version: "deposit-quantile-model-2.0",
      training_period_end: "202605",
    },
    ai_explanation: {
      status: "generated",
      provider: "gemini",
      model: "gemini-test",
      overview: "공식 데이터와 규칙 결과를 바탕으로 확인 순서를 정리했습니다.",
      caution: "최신 등기부와 보증 가입 조건을 직접 확인하세요.",
      limitation: "법률 자문이나 보증 심사를 대신하지 않습니다.",
      privacy_note: "개인정보를 제외하고 생성했습니다.",
      message: null,
      sources: [],
    },
    documents: documentBundle(includeContract),
    corrections: [],
    disclaimer: "이 결과는 계약 판단을 돕는 참고 정보입니다.",
    history_saved: options?.historySaved ?? false,
    history_expires_at: options?.historySaved ? "2026-11-26T00:00:00Z" : null,
  };
}
