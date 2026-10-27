// Public reconstruction of the displayed report values supplied by the user.
// Never copy names, real addresses, original evidence or private PDFs here.
export const maskedAddress = "서울특별시 예시구 안심로 16";
const maskedLot = "서울특별시 예시구 예시동 100";

function source(label: string, field: string, raw_text: string, document = "registry", page = 1) {
  return {
    label, field, raw_text, document, page, section: "공개용 마스킹 예시",
    extraction_method: document === "registry" ? "pdf_text" : "ocr",
    confidence: document === "registry" ? 1 : 0.95,
    corrected: false, previous_value: null, corrected_value: null,
  };
}

export function maskedApartmentBundle() {
  const evidence = { page: 1, section: "공개용 마스킹 예시", raw_text: maskedAddress, extraction_method: "pdf_text", confidence: 1 };
  return {
    registry: {
      property: { road_address: maskedAddress, lot_address: maskedLot, building_name: "샘플아파트", unit: "101동 201호" },
      evidence: { road_address: evidence },
      ownership: [{ owner_name: "가상소유자 E", role: "owner", status: "active", evidence }],
      encumbrances: [], confidence: 1, needs_review: [],
    },
    building_ledger: {
      property: { road_address: maskedAddress, lot_address: maskedLot, building_name: "샘플아파트", unit: "101동 201호", floor: 2, exclusive_area: 84, main_use: "아파트", structure: "철근콘크리트", households: null, approval_date: null, is_illegal_building: null },
      evidence: { road_address: { ...evidence, confidence: 0.95, extraction_method: "ocr" } },
      confidence: 0.95, needs_review: [],
    },
    lease_contract: null, cross_checks: [],
  };
}

export function maskedApartmentResult() {
  const documents = maskedApartmentBundle();
  return {
    analysis_id: "MASKED01-PUBLIC-PREVIEW", mode: "precheck", status: "needs_review",
    score: 4, grade: "낮음", headline: "현재 확인된 위험 신호는 낮습니다",
    summary: "예상 주택가액 대비 보증금은 32%, 근저당을 합친 부담은 32%입니다. 점수는 위험 신호의 우선순위를 보여주며 법률적 안전을 보장하지 않습니다.",
    facts: {
      owner: "가상소유자 E", contract_owner: null, mortgage_amount: 0,
      deposit: 150_000_000, monthly_rent: 2_000_000,
      estimated_value: 470_000_000, estimated_value_low: 390_000_000, estimated_value_high: 860_000_000,
      building_use: "아파트", is_illegal_building: null, approval_year: null,
      recent_transactions: 27, local_price_volatility: 0.585,
    },
    signals: [{
      id: "volatility", severity: "notice", title: "인근 가격 변동성이 있어요",
      description: "단일 시세 대신 복수의 감정·거래 자료를 비교하세요.",
      evidence: "최근 가격 변동성 58.5%", points: 4, sources: [],
    }],
    checks: [
      {
        label: "등기 소유자 확인", status: "verified", detail: "등기부에서 현재 소유자를 확인했습니다.",
        sources: [
          ...["A", "B", "C", "D"].map((name, index) => source("신탁 전 소유자", `ownership.${index}`, `소유자 가상소유자 ${name}`, "registry", index < 2 ? 4 : index + 3)),
          source("등기 소유자", "ownership.current", "소유자 가상소유자 E", "registry", 6),
          source("신탁 전 소유자", "ownership.evidence", "소유권 이전 관련 원문 · [이름·등록번호 등 식별정보 마스킹]", "registry", 4),
        ], comparisons: [], next_step: null,
      },
      {
        label: "입력 주소와 두 문서", status: "verified", detail: "입력 주소와 두 문서의 도로명주소가 일치합니다.",
        sources: [
          source("등기부 도로명주소", "road_address", maskedAddress, "registry", 9),
          source("등기부 지번주소", "lot_address", `[집합건물] ${maskedLot} 샘플아파트 제101동 제2층 제201호`, "registry", 10),
          source("건축물대장 도로명주소", "road_address", `${maskedAddress}(예시동)`, "building_ledger", 1),
          source("건축물대장 지번주소", "lot_address", `${maskedLot} 외 1필지`, "building_ledger", 1),
        ], comparisons: [], next_step: null,
      },
      { label: "위반건축물 여부", status: "needs_review", detail: "위반건축물 여부를 추출하지 못했습니다.", sources: [], comparisons: [], next_step: null },
      { label: "보증보험 가입", status: "needs_review", detail: "보증기관에서 추가 확인이 필요합니다.", sources: [], comparisons: [], next_step: null },
      { label: "등기 권리관계", status: "verified", detail: "분석 대상 권리 중 활성 압류·가압류·신탁·전세권·임차권·경매개시를 찾지 못했습니다 · 말소 7건 제외", sources: [], comparisons: [], next_step: null },
      { label: "공식 건축물대장", status: "needs_review", detail: "건축HUB 표제부 기관에서 HTTP 503 오류를 반환했습니다.", sources: [], comparisons: [], next_step: null },
    ],
    actions: ["잔금 지급 직전 최신 등기부등본을 다시 확인하세요.", "HUG 등 보증기관에서 보증 가입 가능 여부를 직접 확인하세요."],
    market_data: { status: "available", message: "비교 거래 27건 기준의 표시값을 재현한 공개용 화면입니다.", source: "국토교통부", method: "유사 면적 거래 중간가격", as_of: null },
    deposit_market: { status: "out_of_scope", message: "현재 보증금 모델은 서울 연립·다세대 신고자료만 지원하므로 아파트에는 적용하지 않습니다.", expected_deposit: null, upper_deposit: null, upper_ratio: null, exceeds_upper: null, source: "국토교통부 전월세 신고자료", model_version: null, training_period_end: null },
    ai_explanation: {
      status: "generated", provider: "gemini", model: "masked-display-example",
      overview: "인근 가격 변동성 신호가 확인되었으며 일부 공공데이터는 추가 검토가 필요한 상태입니다.",
      caution: "잔금 지급 직전 최신 등기부등본을 다시 확인하고 보증기관에서 보증 가입 가능 여부를 직접 확인해 보세요.",
      limitation: "이 설명은 법률적 판단이나 보장을 대신하지 않으며 확인하지 못한 데이터가 있을 수 있습니다.",
      privacy_note: "Gemini는 판단에 관여하지 않으며 원본 문서·주소·이름·금액을 전송하지 않았습니다.",
      message: null,
      sources: [
        { id: "hug-price-check", organization: "주택도시보증공사(HUG)", title: "주택가격과 보증금 확인 방법", url: "https://m.khug.or.kr/jeonse/web/s03/s030104.jsp", summary: "주택가격과 보증금 확인 안내" },
        { id: "hug-guarantee-overview", organization: "주택도시보증공사(HUG)", title: "전세보증금반환보증 상품개요", url: "https://www.khug.or.kr/hug/web/ig/dr/igdr000001.jsp", summary: "반환보증 상품 안내" },
        { id: "government-building-ledger", organization: "정부24", title: "건축물대장 발급·열람", url: "https://www.gov.kr/mw/AA020InfoCappView.do?CappBizCD=15000000098&tp_seq=03", summary: "건축물대장 원문 확인" },
      ],
    },
    documents, corrections: [],
    disclaimer: "이 사전점검 결과는 입력 조건과 현재 서류를 바탕으로 한 참고 정보이며 계약서 교차검증, 법률 자문 또는 보증 가입 심사를 대신하지 않습니다.",
    history_saved: true, history_expires_at: null,
  };
}
