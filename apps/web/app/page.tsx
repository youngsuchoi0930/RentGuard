"use client";

import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Building2,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  FileCheck2,
  FileText,
  Info,
  LoaderCircle,
  LockKeyhole,
  MapPin,
  Menu,
  PenLine,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  X,
} from "lucide-react";
import { ChangeEvent, useEffect, useMemo, useState } from "react";

type Stage = "form" | "extracting" | "review" | "analyzing" | "result";
type AnalysisMode = "precheck" | "contract_review";
type DocKey = "registry" | "building_ledger" | "lease_contract";
type RegistryRightType = "mortgage" | "seizure" | "provisional_seizure" | "trust" | "leasehold" | "tenant_registration" | "auction" | "other";

type ScalarValue = string | number | boolean | null;

type SourceEvidence = {
  page: number;
  section: string;
  raw_text: string;
  extraction_method: "pdf_text" | "ocr";
  confidence: number;
};

type ReviewItem = { code: string; severity: "info" | "warning" | "blocking"; message: string };

type RegistryExtraction = {
  property: { road_address: string | null; lot_address: string | null; building_name: string | null; unit: string | null };
  evidence: Record<string, SourceEvidence>;
  ownership: Array<{ owner_name: string; status: "active" | "cancelled" | "unknown"; evidence: SourceEvidence | null; rank?: string | null; share?: string | null; registered_at?: string | null }>;
  encumbrances: Array<{ right_type: RegistryRightType; maximum_claim_amount: number | null; status: "active" | "cancelled" | "unknown"; evidence: SourceEvidence | null; rank?: string | null; holder?: string | null; debtor?: string | null; registered_at?: string | null }>;
  confidence: number;
  needs_review: ReviewItem[];
  [key: string]: unknown;
};

type BuildingExtraction = {
  property: { road_address: string | null; lot_address: string | null; building_name: string | null; unit: string | null; floor: number | null; exclusive_area: number | null; main_use: string | null; structure: string | null; households: number | null; approval_date: string | null; is_illegal_building: boolean | null };
  evidence: Record<string, SourceEvidence>;
  confidence: number;
  needs_review: ReviewItem[];
  [key: string]: unknown;
};

type LeaseExtraction = {
  property: { address: string | null; building_description: string | null; leased_part: string | null };
  evidence: Record<string, SourceEvidence>;
  parties: Array<{ role: "landlord" | "tenant" | "agent"; name: string; evidence: SourceEvidence | null }>;
  deposit: { value: number | null; evidence: SourceEvidence | null };
  monthly_rent: { value: number | null; evidence: SourceEvidence | null };
  confidence: number;
  needs_review: ReviewItem[];
  [key: string]: unknown;
};

type DocumentBundle = {
  registry: RegistryExtraction;
  building_ledger: BuildingExtraction;
  lease_contract: LeaseExtraction | null;
  cross_checks: Array<{ id: string; status: string; label: string; detail: string; values: Record<string, ScalarValue> }>;
};

type UserCorrection = {
  field: string;
  label: string;
  previous_value: ScalarValue;
  corrected_value: ScalarValue;
};

type EvidenceReference = {
  document: DocKey;
  field: string;
  label: string;
  page: number | null;
  section: string | null;
  raw_text: string | null;
  extraction_method: "pdf_text" | "ocr" | null;
  confidence: number | null;
  corrected: boolean;
  previous_value: ScalarValue;
  corrected_value: ScalarValue;
};

type AddressSuggestion = {
  road_address: string;
  jibun_address: string;
  zip_code: string;
  building_name: string | null;
};

type Analysis = {
  analysis_id: string;
  mode: AnalysisMode;
  status: "complete" | "partial" | "needs_review";
  score: number;
  grade: "낮음" | "주의" | "높음";
  headline: string;
  summary: string;
  facts: {
    owner: string | null;
    contract_owner: string | null;
    mortgage_amount: number;
    deposit: number;
    monthly_rent: number;
    estimated_value: number | null;
    estimated_value_low: number | null;
    estimated_value_high: number | null;
    building_use: string | null;
    is_illegal_building: boolean | null;
    approval_year: number | null;
    recent_transactions: number | null;
    local_price_volatility: number | null;
  };
  signals: Array<{
    id: string;
    severity: "safe" | "notice" | "warning" | "danger";
    title: string;
    description: string;
    evidence: string;
    points: number;
    sources: EvidenceReference[];
  }>;
  checks: Array<{
    label: string;
    status: "verified" | "warning" | "needs_review";
    detail: string;
    sources: EvidenceReference[];
  }>;
  actions: string[];
  market_data: {
    status: "not_connected" | "available" | "unavailable";
    message: string;
    source: string | null;
    method: string | null;
    as_of: string | null;
  };
  deposit_market: {
    status: "available" | "unavailable" | "out_of_scope";
    message: string;
    expected_deposit: number | null;
    upper_deposit: number | null;
    upper_ratio: number | null;
    exceeds_upper: boolean | null;
    source: string;
    model_version: string | null;
    training_period_end: string | null;
  };
  ai_explanation: {
    status: "generated" | "unavailable" | "disabled";
    provider: "gemini";
    model: string;
    overview: string | null;
    caution: string | null;
    limitation: string | null;
    privacy_note: string | null;
    message: string | null;
  };
  documents: DocumentBundle;
  corrections: UserCorrection[];
  disclaimer: string;
};

const DOCUMENTS: Array<{ key: DocKey; label: string; hint: string }> = [
  { key: "registry", label: "등기부등본", hint: "소유권·근저당 확인" },
  { key: "building_ledger", label: "건축물대장", hint: "용도·위반 여부 확인" },
  { key: "lease_contract", label: "임대차계약서", hint: "계약자·보증금 확인" },
];

const RIGHT_LABELS: Record<RegistryRightType, string> = {
  mortgage: "근저당권",
  seizure: "압류",
  provisional_seizure: "가압류",
  trust: "신탁",
  leasehold: "전세권",
  tenant_registration: "임차권등기",
  auction: "경매개시결정",
  other: "기타 권리",
};

function money(value: number | null) {
  if (value === null) return "미연동";
  if (value >= 100000000) {
    const eok = value / 100000000;
    return `${Number.isInteger(eok) ? eok : eok.toFixed(1)}억원`;
  }
  return `${Math.round(value / 10000).toLocaleString("ko-KR")}만원`;
}

function parseMoney(value: string) {
  return Number(value.replace(/[^0-9]/g, "")) || 0;
}

function formatInput(value: string) {
  const digits = value.replace(/[^0-9]/g, "");
  return digits ? Number(digits).toLocaleString("ko-KR") : "";
}

function addressUnit(value: string) {
  return value.match(/[가-힣A-Za-z0-9-]*\d{1,5}\s*호\b/)?.[0] ?? "";
}

function nestedValue(source: unknown, path: string): ScalarValue {
  let cursor: unknown = source;
  for (const part of path.split(".")) {
    if (cursor === null || typeof cursor !== "object") return null;
    cursor = (cursor as Record<string, unknown>)[part];
  }
  return typeof cursor === "string" || typeof cursor === "number" || typeof cursor === "boolean" || cursor === null
    ? cursor
    : null;
}

function withNestedValue<T>(source: T, path: string, value: ScalarValue): T {
  const copy = structuredClone(source);
  const parts = path.split(".");
  let cursor = copy as Record<string, unknown>;
  parts.slice(0, -1).forEach((part) => {
    cursor = cursor[part] as Record<string, unknown>;
  });
  cursor[parts.at(-1) as string] = value;
  return copy;
}

function documentName(key: DocKey) {
  return key === "registry" ? "등기부등본" : key === "building_ledger" ? "건축물대장" : "임대차계약서";
}

function EvidenceList({ sources }: { sources: EvidenceReference[] }) {
  if (!sources.length) return null;
  return (
    <div className="evidence-list">
      {sources.map((source, index) => (
        <div className="evidence-item" key={`${source.field}-${index}`}>
          <div>
            <strong>{source.label}</strong>
            <span>{documentName(source.document)}{source.page ? ` · ${source.page}페이지` : ""}{source.confidence !== null ? ` · 신뢰도 ${Math.round(source.confidence * 100)}%` : ""}</span>
          </div>
          {source.raw_text && <q>{conciseEvidence(source)}</q>}
          {source.corrected && <small>사용자 수정: {String(source.previous_value ?? "미추출")} → {String(source.corrected_value ?? "미입력")}</small>}
        </div>
      ))}
    </div>
  );
}

function conciseEvidence(source: EvidenceReference) {
  const raw = source.raw_text?.replace(/\s+/g, " ").trim() ?? "";
  if (source.field.includes("maximum_claim_amount")) {
    const amount = raw.match(/채권\s*최고액\s*(?:금)?\s*[0-9OIl,. ]+\s*원/i)?.[0];
    if (amount) return `등기부 기재: ${amount.replace(/\s+/g, " ").trim()}`;
  }
  return raw.length > 140 ? `${raw.slice(0, 137)}…` : raw;
}

function prepareForReview(bundle: DocumentBundle) {
  const prepared = structuredClone(bundle);
  if (prepared.registry.ownership.length === 0) {
    prepared.registry.ownership.push({
      owner_name: "",
      status: "active",
      evidence: null,
    });
  }
  if (prepared.lease_contract && !prepared.lease_contract.parties.some((party) => party.role === "landlord")) {
    prepared.lease_contract.parties.push({ role: "landlord", name: "", evidence: null });
  }
  return prepared;
}

function ReviewField({
  label,
  value,
  evidence,
  moneyField = false,
  numericField = false,
  onChange,
}: {
  label: string;
  value: string | number | null;
  evidence?: SourceEvidence | null;
  moneyField?: boolean;
  numericField?: boolean;
  onChange: (value: string | number | null) => void;
}) {
  const displayed = moneyField && typeof value === "number" ? value.toLocaleString("ko-KR") : String(value ?? "");
  return (
    <label className="review-field">
      <span>{label}{evidence && <small>{evidence.page}페이지 · {Math.round(evidence.confidence * 100)}%</small>}</span>
      <input
        value={displayed}
        inputMode={moneyField ? "numeric" : numericField ? "decimal" : undefined}
        placeholder="추출하지 못함"
        onChange={(event) => {
          if (moneyField) {
            const digits = event.target.value.replace(/[^0-9]/g, "");
            onChange(digits ? Number(digits) : null);
          } else if (numericField) {
            const number = Number(event.target.value.replace(/[^0-9.]/g, ""));
            onChange(Number.isFinite(number) && event.target.value.trim() ? number : null);
          } else {
            onChange(event.target.value || null);
          }
        }}
      />
      {evidence?.raw_text && <q>{evidence.raw_text}</q>}
    </label>
  );
}

export default function HomePage() {
  const [stage, setStage] = useState<Stage>("form");
  const [analysisMode, setAnalysisMode] = useState<AnalysisMode>("precheck");
  const [mobileMenu, setMobileMenu] = useState(false);
  const [address, setAddress] = useState("");
  const [deposit, setDeposit] = useState("");
  const [monthlyRent, setMonthlyRent] = useState("");
  const [files, setFiles] = useState<Partial<Record<DocKey, File>>>({});
  const [progress, setProgress] = useState(0);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [documents, setDocuments] = useState<DocumentBundle | null>(null);
  const [originalDocuments, setOriginalDocuments] = useState<DocumentBundle | null>(null);
  const [corrections, setCorrections] = useState<UserCorrection[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [expandedSignal, setExpandedSignal] = useState<string | null>(null);
  const [addressSuggestions, setAddressSuggestions] = useState<AddressSuggestion[]>([]);
  const [isSearchingAddress, setIsSearchingAddress] = useState(false);

  const requiredDocuments = analysisMode === "precheck" ? DOCUMENTS.slice(0, 2) : DOCUMENTS;
  const uploadedCount = requiredDocuments.filter((document) => files[document.key]).length;
  const canAnalyze = address.trim().length >= 5
    && parseMoney(deposit) > 0
    && requiredDocuments.every((document) => files[document.key]);
  const hasMarketData = analysis?.market_data.status === "available" && analysis.facts.estimated_value !== null;
  const steps = useMemo(() => [
    { label: "계약 정보", done: stage !== "form", current: stage === "form" },
    { label: "추출값 확인", done: stage === "analyzing" || stage === "result", current: stage === "extracting" || stage === "review" },
    { label: "위험 리포트", done: false, current: stage === "result" },
  ], [stage]);

  useEffect(() => {
    if (stage !== "extracting" && stage !== "analyzing") return;
    const timer = window.setInterval(() => {
      setElapsedSeconds((current) => current + 1);
      setProgress((current) => Math.min(current + (current < 35 ? 6 : current < 70 ? 2 : 1), 94));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [stage]);

  const handleFile = (key: DocKey, event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setError("현재 실제 분석은 PDF 파일만 지원합니다.");
      event.currentTarget.value = "";
      return;
    }
    if (file.size > 20 * 1024 * 1024) {
      setError("파일은 문서당 20MB 이하만 업로드할 수 있습니다.");
      event.currentTarget.value = "";
      return;
    }
    setError(null);
    setFiles((current) => ({ ...current, [key]: file }));
  };

  const searchAddress = async () => {
    if (address.trim().length < 2) {
      setError("도로명이나 지번을 두 글자 이상 입력해주세요.");
      return;
    }
    setError(null);
    setAddressSuggestions([]);
    setIsSearchingAddress(true);
    try {
      const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const response = await fetch(`${apiBase}/api/v1/addresses/search?keyword=${encodeURIComponent(address.trim())}`);
      if (!response.ok) {
        const payload = await response.json().catch(() => null) as { detail?: string } | null;
        throw new Error(payload?.detail || "주소 검색에 실패했습니다.");
      }
      const payload = await response.json() as { items: AddressSuggestion[] };
      setAddressSuggestions(payload.items);
      if (payload.items.length === 0) setError("검색 결과가 없습니다. 도로명과 건물번호를 확인해주세요.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "주소 검색에 실패했습니다.");
    } finally {
      setIsSearchingAddress(false);
    }
  };

  const runExtraction = async () => {
    if (!canAnalyze) {
      setError(`주소와 보증금을 입력하고 PDF 문서 ${requiredDocuments.length}개를 모두 올려주세요.`);
      return;
    }

    setError(null);
    setAnalysis(null);
    setDocuments(null);
    setOriginalDocuments(null);
    setCorrections([]);
    setProgress(4);
    setElapsedSeconds(0);
    setStage("extracting");

    const formData = new FormData();
    formData.set("address", address);
    formData.set("deposit", String(parseMoney(deposit)));
    formData.set("monthly_rent", String(parseMoney(monthlyRent)));
    formData.set("analysis_mode", analysisMode);
    requiredDocuments.forEach(({ key }) => {
      const file = files[key];
      if (file) formData.set(key, file);
    });

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/document-bundles/extract`, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
        const detail = typeof payload?.detail === "string" ? payload.detail : `분석 요청에 실패했습니다. (${response.status})`;
        throw new Error(detail);
      }
      const result = prepareForReview(await response.json() as DocumentBundle);
      setDocuments(result);
      setOriginalDocuments(structuredClone(result));
      setProgress(100);
      setStage("review");
    } catch (cause) {
      const message = cause instanceof Error && cause.message !== "Failed to fetch"
        ? cause.message
        : "분석 API에 연결할 수 없습니다. API 서버가 실행 중인지 확인해주세요.";
      setError(message);
      setProgress(0);
      setStage("form");
    }
  };

  const updateExtractedValue = (path: string, label: string, value: ScalarValue) => {
    if (!documents || !originalDocuments) return;
    const previousValue = nestedValue(originalDocuments, path);
    setDocuments(withNestedValue(documents, path, value));
    setCorrections((current) => {
      const withoutField = current.filter((item) => item.field !== path);
      return previousValue === value
        ? withoutField
        : [...withoutField, { field: path, label, previous_value: previousValue, corrected_value: value }];
    });
  };

  const submitAnalysis = async () => {
    if (!documents) {
      setError("먼저 문서 추출을 완료해주세요.");
      setStage("form");
      return;
    }
    setError(null);
    setProgress(54);
    setElapsedSeconds(0);
    setStage("analyzing");
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/analyses/from-extractions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode: analysisMode,
          address,
          deposit: parseMoney(deposit),
          monthly_rent: parseMoney(monthlyRent),
          documents,
          corrections,
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
        const detail = typeof payload?.detail === "string" ? payload.detail : `분석 요청에 실패했습니다. (${response.status})`;
        throw new Error(detail);
      }
      const result = await response.json() as Analysis;
      setAnalysis(result);
      setExpandedSignal(result.signals[0]?.id ?? null);
      setProgress(100);
      setStage("result");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "분석 요청에 실패했습니다.");
      setProgress(0);
      setStage("review");
    }
  };

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileMenu ? "open" : ""}`}>
        <div className="brand">
          <div className="brand-mark"><ShieldCheck size={21} strokeWidth={2.4} /></div>
          <div><strong>RentGuard</strong><span>AI 계약안전 진단</span></div>
        </div>
        <button className="close-menu" onClick={() => setMobileMenu(false)} aria-label="메뉴 닫기"><X size={20} /></button>

        <nav>
          <p className="nav-label">서비스</p>
          <button className="nav-item active"><FileCheck2 size={19} />새 계약 분석</button>
          <button className="nav-item"><Search size={19} />분석 기록</button>
          <button className="nav-item"><CircleHelp size={19} />계약 가이드</button>
        </nav>

        <div className="sidebar-guide">
          <div className="guide-icon"><LockKeyhole size={19} /></div>
          <strong>내 서류는 안전하게</strong>
          <p>분석이 끝난 원본 문서는 서버에 보관하지 않습니다.</p>
          <button>보안 원칙 보기 <ArrowRight size={14} /></button>
        </div>

        <div className="profile">
          <div className="avatar">민</div>
          <div><strong>김민지</strong><span>무료 플랜</span></div>
          <ChevronDown size={17} />
        </div>
      </aside>

      {mobileMenu && <button className="scrim" onClick={() => setMobileMenu(false)} aria-label="메뉴 닫기" />}

      <main>
        <header className="topbar">
          <button className="menu-button" onClick={() => setMobileMenu(true)} aria-label="메뉴 열기"><Menu /></button>
          <div className="mobile-brand"><ShieldCheck size={20} /><strong>RentGuard</strong></div>
          <div className="trust-note"><span className="live-dot" /> 업로드 문서 원문 기반 분석</div>
          <button className="help-button"><CircleHelp size={17} /> 도움이 필요해요</button>
        </header>

        <div className="page-wrap">
          <div className="stepper" aria-label="분석 단계">
            {steps.map((step, index) => (
              <div className={`step ${step.current ? "current" : ""} ${step.done ? "done" : ""}`} key={step.label}>
                <span>{step.done ? <Check size={14} /> : index + 1}</span>
                <b>{step.label}</b>
                {index < steps.length - 1 && <i />}
              </div>
            ))}
          </div>

          {stage === "form" && (
            <section className="form-stage">
              {error && <div className="error-banner" role="alert"><AlertTriangle size={18} />{error}</div>}
              <div className="page-heading">
                <div className="eyebrow"><Sparkles size={15} /> AI 부동산 서류 점검</div>
                <h1>계약하기 전,<br /><em>서류 속 위험</em>을 먼저 확인하세요.</h1>
                <p>계약서가 없어도 사전점검을 시작하고, 계약서가 생기면 문서끼리 교차검증할 수 있어요.</p>
              </div>

              <div className="mode-picker" role="group" aria-label="분석 방식 선택">
                <button type="button" className={analysisMode === "precheck" ? "active" : ""} aria-pressed={analysisMode === "precheck"} onClick={() => { setAnalysisMode("precheck"); setError(null); }}>
                  <span>추천 · 계약 전</span>
                  <strong>사전점검</strong>
                  <small>등기부등본 + 건축물대장</small>
                </button>
                <button type="button" className={analysisMode === "contract_review" ? "active" : ""} aria-pressed={analysisMode === "contract_review"} onClick={() => { setAnalysisMode("contract_review"); setError(null); }}>
                  <span>계약서 작성 후</span>
                  <strong>계약서 교차검증</strong>
                  <small>계약서까지 포함한 서류 3종</small>
                </button>
              </div>

              <div className="form-grid">
                <div className="form-card">
                  <div className="card-title"><span>1</span><div><h2>계약 조건을 알려주세요</h2><p>{analysisMode === "precheck" ? "예정한 보증금과 월세를 입력해주세요." : "계약서에 적힌 내용을 그대로 입력해주세요."}</p></div></div>
                  <label className="field-label" htmlFor="address">집 주소</label>
                  <div className="address-field">
                    <div className="input-shell"><MapPin size={19} /><input id="address" placeholder="점검할 집의 도로명주소" value={address} onChange={(e) => { setAddress(e.target.value); setAddressSuggestions([]); }} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); void searchAddress(); } }} /><button type="button" onClick={searchAddress} disabled={isSearchingAddress}>{isSearchingAddress ? "검색 중" : "주소 찾기"}</button></div>
                    {addressSuggestions.length > 0 && (
                      <div className="address-results" role="listbox" aria-label="주소 검색 결과">
                        {addressSuggestions.map((item) => (
                          <button type="button" key={`${item.road_address}-${item.jibun_address}`} onClick={() => { const unit = addressUnit(address); setAddress(`${item.road_address}${unit ? `, ${unit}` : ""}`); setAddressSuggestions([]); setError(null); }}>
                            <span><b>도로명</b>{item.road_address}</span>
                            <span><b>지번</b>{item.jibun_address}</span>
                            <small>우편번호 {item.zip_code}{item.building_name ? ` · ${item.building_name}` : ""}</small>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="money-grid">
                    <div>
                      <label className="field-label" htmlFor="deposit">보증금</label>
                      <div className="input-shell"><input id="deposit" inputMode="numeric" placeholder="150,000,000" value={deposit} onChange={(e) => setDeposit(formatInput(e.target.value))} /><span>원</span></div>
                    </div>
                    <div>
                      <label className="field-label" htmlFor="rent">월세</label>
                      <div className="input-shell"><input id="rent" inputMode="numeric" placeholder="100,000" value={monthlyRent} onChange={(e) => setMonthlyRent(formatInput(e.target.value))} /><span>원</span></div>
                    </div>
                  </div>
                  <div className="mini-summary">
                    <Info size={16} /> {parseMoney(deposit) > 0 ? `${money(parseMoney(deposit))} 보증부 계약으로 분석합니다.` : analysisMode === "precheck" ? "예정 보증금을 입력하면 시세와 근저당에 함께 대입합니다." : "보증금을 입력하면 계약서 추출값과 비교합니다."}
                  </div>
                </div>

                <div className="form-card documents-card">
                  <div className="card-title"><span>2</span><div><h2>{analysisMode === "precheck" ? "확인 서류를 올려주세요" : "계약 서류를 올려주세요"}</h2><p>PDF · 파일당 최대 20MB</p></div><div className="count-badge">{uploadedCount}/{requiredDocuments.length}</div></div>
                  <div className="document-list">
                    {requiredDocuments.map((doc) => {
                      const file = files[doc.key];
                      return (
                        <label className={`document-row ${file ? "uploaded" : ""}`} key={doc.key}>
                          <input type="file" accept=".pdf,application/pdf" onChange={(event) => handleFile(doc.key, event)} />
                          <div className="doc-icon">{file ? <FileCheck2 size={21} /> : <FileText size={21} />}</div>
                          <div className="doc-copy"><strong>{file?.name ?? doc.label}</strong><span>{file ? `${(file.size / 1024 / 1024).toFixed(1)}MB · 업로드 완료` : doc.hint}</span></div>
                          <div className="upload-action">{file ? <Check size={17} /> : <><Plus size={16} /><span>추가</span></>}</div>
                        </label>
                      );
                    })}
                  </div>
                  <div className="sample-note"><UploadCloud size={18} /><div><strong>{analysisMode === "precheck" ? "계약서 없이 사전점검할 수 있어요" : "PDF 세 종류가 모두 필요해요"}</strong><span>{analysisMode === "precheck" ? "입력 조건과 등기부·건축물대장을 기준으로 분석합니다." : "계약서 내용까지 추출해 문서끼리 대조합니다."}</span></div></div>
                </div>
              </div>

              <div className="form-footer">
                <div><ShieldCheck size={18} /><span>원본 파일은 분석 후 즉시 삭제됩니다.</span></div>
                <button className="primary-button" disabled={!canAnalyze} onClick={runExtraction}>문서에서 값 추출하기 <ArrowRight size={19} /></button>
              </div>
            </section>
          )}

          {stage === "review" && documents && (
            <section className="review-stage">
              {error && <div className="error-banner" role="alert"><AlertTriangle size={18} />{error}</div>}
              <div className="review-header">
                <button className="back-button" onClick={() => setStage("form")}><ArrowLeft size={17} /> 파일 다시 선택</button>
                <div>
                  <div className="eyebrow"><FileCheck2 size={15} /> 추출 완료 · 사용자 확인 단계</div>
                  <h1>분석 전에 추출값을 확인해주세요</h1>
                  <p>틀린 값만 수정하면 됩니다. 수정 내역은 결과 근거에 함께 표시돼요.</p>
                </div>
                <div className={`correction-badge ${corrections.length ? "changed" : ""}`}>{corrections.length}개 수정</div>
              </div>

              <div className="review-grid">
                <article className="review-card">
                  <div className="review-card-head"><div className="doc-icon"><FileText size={20} /></div><div><strong>등기부등본</strong><span>소유자·주소·근저당</span></div><small>신뢰도 {Math.round(documents.registry.confidence * 100)}%</small></div>
                  <ReviewField label="도로명주소" value={documents.registry.property.road_address} evidence={documents.registry.evidence.road_address} onChange={(value) => updateExtractedValue("registry.property.road_address", "등기부 도로명주소", value)} />
                  <ReviewField label="현재 소유자" value={documents.registry.ownership[0]?.owner_name ?? null} evidence={documents.registry.ownership[0]?.evidence} onChange={(value) => updateExtractedValue("registry.ownership.0.owner_name", "등기 소유자", value)} />
                  {documents.registry.encumbrances.filter((entry) => entry.right_type === "mortgage" && entry.status === "active").map((entry) => {
                    const index = documents.registry.encumbrances.indexOf(entry);
                    return <ReviewField key={`mortgage-${index}`} label={`근저당 채권최고액${index > 0 ? ` ${index + 1}` : ""}`} value={entry.maximum_claim_amount} evidence={entry.evidence} moneyField onChange={(value) => updateExtractedValue(`registry.encumbrances.${index}.maximum_claim_amount`, "근저당 채권최고액", value)} />;
                  })}
                  {!documents.registry.encumbrances.some((entry) => entry.right_type === "mortgage" && entry.status === "active") && <div className="empty-extraction"><CheckCircle2 size={16} /> 추출된 활성 근저당권이 없습니다.</div>}
                  {documents.registry.encumbrances.some((entry) => entry.right_type !== "mortgage") && (
                    <div className="registry-right-list">
                      <strong>기타 등기 권리</strong>
                      {documents.registry.encumbrances.filter((entry) => entry.right_type !== "mortgage").map((entry, index) => (
                        <div className={entry.status} key={`${entry.right_type}-${entry.rank ?? index}`}>
                          <span>{RIGHT_LABELS[entry.right_type]}</span>
                          <small>{entry.rank ? `순위 ${entry.rank}번` : "순위 미추출"}{entry.registered_at ? ` · ${entry.registered_at}` : ""}</small>
                          <em>{entry.status === "cancelled" ? "말소" : entry.status === "active" ? "활성" : "확인 필요"}</em>
                        </div>
                      ))}
                    </div>
                  )}
                </article>

                <article className="review-card">
                  <div className="review-card-head"><div className="doc-icon"><Building2 size={20} /></div><div><strong>건축물대장</strong><span>주소·용도·위반 여부</span></div><small>신뢰도 {Math.round(documents.building_ledger.confidence * 100)}%</small></div>
                  <ReviewField label="도로명주소" value={documents.building_ledger.property.road_address} evidence={documents.building_ledger.evidence.road_address} onChange={(value) => updateExtractedValue("building_ledger.property.road_address", "건축물대장 도로명주소", value)} />
                  <ReviewField label="호수" value={documents.building_ledger.property.unit} evidence={documents.building_ledger.evidence.unit} onChange={(value) => updateExtractedValue("building_ledger.property.unit", "건축물대장 호수", value)} />
                  <ReviewField label="전용면적(㎡)" value={documents.building_ledger.property.exclusive_area} evidence={documents.building_ledger.evidence.exclusive_area} numericField onChange={(value) => updateExtractedValue("building_ledger.property.exclusive_area", "전용면적", value)} />
                  <ReviewField label="주용도" value={documents.building_ledger.property.main_use} evidence={documents.building_ledger.evidence.main_use} onChange={(value) => updateExtractedValue("building_ledger.property.main_use", "건축물 주용도", value)} />
                  <ReviewField label="사용승인일" value={documents.building_ledger.property.approval_date} evidence={documents.building_ledger.evidence.approval_date} onChange={(value) => updateExtractedValue("building_ledger.property.approval_date", "사용승인일", value)} />
                  <label className="review-field">
                    <span>위반건축물 여부{documents.building_ledger.evidence.is_illegal_building && <small>{documents.building_ledger.evidence.is_illegal_building.page}페이지 · {Math.round(documents.building_ledger.evidence.is_illegal_building.confidence * 100)}%</small>}</span>
                    <select value={documents.building_ledger.property.is_illegal_building === null ? "unknown" : documents.building_ledger.property.is_illegal_building ? "yes" : "no"} onChange={(event) => updateExtractedValue("building_ledger.property.is_illegal_building", "위반건축물 여부", event.target.value === "unknown" ? null : event.target.value === "yes")}>
                      <option value="unknown">확인하지 못함</option><option value="no">해당 없음</option><option value="yes">위반건축물 해당</option>
                    </select>
                    {documents.building_ledger.evidence.is_illegal_building?.raw_text && <q>{documents.building_ledger.evidence.is_illegal_building.raw_text}</q>}
                  </label>
                </article>

                {documents.lease_contract && (() => {
                  const contract = documents.lease_contract;
                  const landlordIndex = contract.parties.findIndex((party) => party.role === "landlord");
                  const landlord = contract.parties[landlordIndex];
                  return (
                    <article className="review-card">
                      <div className="review-card-head"><div className="doc-icon"><FileCheck2 size={20} /></div><div><strong>임대차계약서</strong><span>임대인·주소·계약 금액</span></div><small>신뢰도 {Math.round(contract.confidence * 100)}%</small></div>
                      <ReviewField label="목적물 주소" value={contract.property.address} evidence={contract.evidence.address} onChange={(value) => updateExtractedValue("lease_contract.property.address", "계약서 목적물 주소", value)} />
                      <ReviewField label="임대인" value={landlord?.name ?? null} evidence={landlord?.evidence} onChange={(value) => updateExtractedValue(`lease_contract.parties.${landlordIndex}.name`, "계약서 임대인", value)} />
                      <ReviewField label="보증금" value={contract.deposit.value} evidence={contract.deposit.evidence} moneyField onChange={(value) => updateExtractedValue("lease_contract.deposit.value", "계약서 보증금", value)} />
                      <ReviewField label="월세" value={contract.monthly_rent.value} evidence={contract.monthly_rent.evidence} moneyField onChange={(value) => updateExtractedValue("lease_contract.monthly_rent.value", "계약서 월세", value)} />
                    </article>
                  );
                })()}
              </div>

              <div className="review-notice"><Info size={17} /><div><strong>원문과 한 번만 대조해주세요</strong><span>페이지와 OCR 원문을 함께 표시했습니다. 사용자가 수정한 값은 자동 추출값과 구분해 결과에 남깁니다.</span></div></div>
              <div className="form-footer review-footer">
                <button className="outline-button" onClick={() => setStage("form")}><ArrowLeft size={16} /> 파일 다시 선택</button>
                <button className="primary-button" onClick={submitAnalysis}>확인한 값으로 위험 분석 <ArrowRight size={19} /></button>
              </div>
            </section>
          )}

          {(stage === "extracting" || stage === "analyzing") && (
            <section className="analyzing-stage">
              <div className="scan-visual">
                <div className="scan-paper"><FileText size={58} /><span className="scan-line" /></div>
                <div className="orbit"><ShieldCheck size={25} /></div>
              </div>
              <div className="eyebrow"><LoaderCircle className="spin" size={15} /> DOCUMENT AI</div>
              <h1>{stage === "extracting" ? <>서류에서 핵심 정보를<br />추출하고 있어요</> : <>공공데이터와 위험도를<br />계산하고 있어요</>}</h1>
              <p>{stage === "extracting" ? "주소·소유자·근저당 등 확인할 값을 찾습니다. 스캔 문서는 몇 분 걸릴 수 있어요." : "확인한 추출값을 공식 데이터와 대조하고 위험 신호를 계산합니다."}</p>
              <div className="progress-shell"><div style={{ width: `${progress}%` }} /></div>
              <strong className="progress-number">{progress}% · {elapsedSeconds}초 경과</strong>
              <div className="analysis-steps">
                <span className={progress > 18 ? "done" : "active"}><CheckCircle2 /> 문서 분류</span>
                <span className={progress > 45 ? "done" : progress > 18 ? "active" : ""}><FileText /> 핵심정보 추출</span>
                <span className={progress > 70 ? "done" : progress > 45 ? "active" : ""}><Building2 /> 공공데이터 대조</span>
                <span className={progress > 90 ? "active" : ""}><ShieldCheck /> 위험도 계산</span>
              </div>
            </section>
          )}

          {stage === "result" && analysis && (
            <section className="result-stage">
              <div className="result-header">
                <button className="back-button" onClick={() => setStage("form")}><ArrowLeft size={17} /> 새 계약 분석</button>
                <div>
                  <div className="eyebrow"><CheckCircle2 size={15} /> {analysis.mode === "precheck" ? "사전점검" : "계약서 교차검증"} · {analysis.status === "complete" ? "분석 완료" : analysis.status === "partial" ? (analysis.market_data.status === "unavailable" ? "비교 거래 부족" : "시세 연동 전") : "확인 필요한 항목 있음"} · {analysis.analysis_id.slice(0, 8)}</div>
                  <h1>{address}</h1>
                  <p>보증금 {money(analysis.facts.deposit)} · 월세 {money(parseMoney(monthlyRent))}</p>
                </div>
                <button className="outline-button" onClick={() => setStage("review")}><RefreshCw size={16} /> 추출값 다시 확인</button>
              </div>

              <div className="report-layout">
                <div className="report-main">
                  <article className="risk-hero">
                    <div className="score-ring" style={{ "--score": analysis.score } as React.CSSProperties}>
                      <div>
                        <span className="score-kicker">위험 점수</span>
                        <strong>{analysis.score}<em>점</em></strong>
                        <span>{hasMarketData ? "100점 기준" : "시세 미반영 임시 점수"}</span>
                      </div>
                    </div>
                    <div className="risk-copy">
                      <span className="danger-pill"><AlertTriangle size={15} /> 종합 위험도 {analysis.grade}</span>
                      <h2>{analysis.headline}</h2>
                      <p>{analysis.summary}</p>
                      {analysis.corrections.length > 0 && <small className="applied-corrections"><CheckCircle2 size={14} /> 사용자 수정 {analysis.corrections.length}건을 반영했습니다</small>}
                    </div>
                  </article>

                  <article className={`ai-explanation-card ${analysis.ai_explanation.status !== "generated" ? "is-unavailable" : ""}`}>
                      <div className="ai-explanation-head">
                        <div><Sparkles size={17} /><span>Gemini 쉬운 설명</span></div>
                        <small>{analysis.ai_explanation.status === "generated" ? "개인정보 제외 후 생성" : "규칙 기반 결과 유지"}</small>
                      </div>
                      {analysis.ai_explanation.status === "generated" && analysis.ai_explanation.overview ? (
                        <>
                          <h2>분석 결과를 쉽게 풀어봤어요</h2>
                          <p>{analysis.ai_explanation.overview}</p>
                          <div className="ai-explanation-points">
                            {analysis.ai_explanation.caution && <div><strong>왜 확인해야 하나요?</strong><span>{analysis.ai_explanation.caution}</span></div>}
                            {analysis.ai_explanation.limitation && <div><strong>어디까지 참고해야 하나요?</strong><span>{analysis.ai_explanation.limitation}</span></div>}
                          </div>
                          {analysis.ai_explanation.privacy_note && <small className="ai-privacy"><LockKeyhole size={13} /> {analysis.ai_explanation.privacy_note}</small>}
                        </>
                      ) : (
                        <>
                          <h2>Gemini 설명을 표시하지 못했어요</h2>
                          <p>{analysis.ai_explanation.message ?? "규칙 기반 분석 결과는 정상적으로 사용할 수 있습니다."}</p>
                          <small className="ai-privacy"><Info size={13} /> 사용 모델: {analysis.ai_explanation.model}</small>
                        </>
                      )}
                  </article>

                  <article className="metric-card">
                    <div className="section-heading"><div><span>핵심 수치</span><h2>돈의 흐름을 먼저 확인했어요</h2></div><button><Info size={16} /> 산정 기준</button></div>
                    <div className="metrics">
                      <div><span>예상 주택가액</span><strong>{money(analysis.facts.estimated_value)}</strong><small>{hasMarketData && analysis.facts.estimated_value_low !== null && analysis.facts.estimated_value_high !== null ? `중간 50% 범위 ${money(analysis.facts.estimated_value_low)} ~ ${money(analysis.facts.estimated_value_high)} · ${analysis.facts.recent_transactions ?? 0}건` : hasMarketData ? `${analysis.facts.recent_transactions ?? 0}건 · ${analysis.market_data.method ?? "실거래 중간가격"}` : analysis.market_data.status === "unavailable" ? "비교 거래 부족" : "공공 실거래가 연동 전"}</small></div>
                      <div><span>근저당 채권최고액</span><strong className="danger-text">{money(analysis.facts.mortgage_amount)}</strong><small>등기부등본 추출</small></div>
                      <div><span>입력 보증금</span><strong>{money(analysis.facts.deposit)}</strong><small>{analysis.mode === "precheck" ? "사용자가 입력한 예정 계약 조건" : "계약서 추출값과 교차검증"}</small></div>
                    </div>
                    {hasMarketData && analysis.facts.estimated_value !== null ? (
                      <div className="burden-bar">
                        <div className="bar-labels"><span>예상 주택가액 {money(analysis.facts.estimated_value)}</span><strong>부담 합계 {money(analysis.facts.mortgage_amount + analysis.facts.deposit)} <em>{Math.round((analysis.facts.mortgage_amount + analysis.facts.deposit) / analysis.facts.estimated_value * 100)}%</em></strong></div>
                        <div className="bar-track"><span className="mortgage-segment" /><span className="deposit-segment" /></div>
                        <div className="legend"><span><i className="legend-mortgage" />근저당</span><span><i className="legend-deposit" />보증금</span><span><i className="legend-limit" />주택가액 100%</span></div>
                      </div>
                    ) : (
                      <div className="market-pending"><Info size={17} /><div><strong>시세 비율은 아직 계산하지 않았어요</strong><span>{analysis.market_data.message}</span></div></div>
                    )}
                    {analysis.deposit_market.status === "available" ? (
                      <div className={`deposit-benchmark ${analysis.deposit_market.exceeds_upper ? "warning" : "normal"}`}>
                        <div className="deposit-benchmark-head">
                          <div>{analysis.deposit_market.exceeds_upper ? <AlertTriangle size={17} /> : <CheckCircle2 size={17} />}<strong>유사 계약 보증금 범위</strong></div>
                          <span>{analysis.deposit_market.exceeds_upper ? "상위 범위 초과" : "예측 범위 안"}</span>
                        </div>
                        <div className="deposit-benchmark-values">
                          <div><span>입력 보증금</span><strong>{money(analysis.facts.deposit)}</strong></div>
                          <div><span>예상 중앙값</span><strong>{money(analysis.deposit_market.expected_deposit)}</strong></div>
                          <div><span>상위 95% 경계</span><strong>{money(analysis.deposit_market.upper_deposit)}</strong></div>
                        </div>
                        <p>{analysis.deposit_market.message} <small>서울 연립·다세대 전월세 신고자료 · 학습기준 {analysis.deposit_market.training_period_end ?? "확인 불가"}</small></p>
                      </div>
                    ) : (
                      <div className="deposit-benchmark unavailable">
                        <div className="deposit-benchmark-head"><div><Info size={17} /><strong>유사 계약 보증금 범위</strong></div><span>판단 보류</span></div>
                        <p>{analysis.deposit_market.message}</p>
                      </div>
                    )}
                  </article>

                  <article className="signals-card">
                    <div className="section-heading"><div><span>발견된 위험 신호</span><h2>왜 주의해야 하는지 알려드려요</h2></div><div className="signal-count">{analysis.signals.length}개 발견</div></div>
                    <div className="signal-list">
                      {analysis.signals.map((signal) => {
                        const open = expandedSignal === signal.id;
                        return (
                          <button className={`signal-row ${signal.severity} ${open ? "open" : ""}`} key={signal.id} onClick={() => setExpandedSignal(open ? null : signal.id)}>
                            <span className="signal-icon">{signal.severity === "notice" ? <Info size={19} /> : <AlertTriangle size={19} />}</span>
                            <div className="signal-copy"><strong>{signal.title}</strong><small>{signal.evidence}</small>{open && <><p><b>쉽게 말하면</b>{signal.description}</p><EvidenceList sources={signal.sources} /></>}</div>
                            <span className="points">{signal.points > 0 ? `+${signal.points}점` : "확인"}</span>
                            <ChevronDown className="chevron" size={18} />
                          </button>
                        );
                      })}
                    </div>
                  </article>
                </div>

                <aside className="report-side">
                  <article className="action-card">
                    <div className="action-card-head"><span><Sparkles size={17} /> 지금 해야 할 일</span><strong>계약 전 행동 {analysis.actions.length}가지</strong></div>
                    <ol>
                      {analysis.actions.map((action, index) => <li key={action}><span>{index + 1}</span><p>{action}</p></li>)}
                    </ol>
                    <button>행동 체크리스트 저장 <ArrowRight size={17} /></button>
                  </article>

                  <article className="checks-card">
                    <div className="section-heading"><div><span>{analysis.mode === "precheck" ? "서류·공공데이터 확인" : "서류 교차검증"}</span><h2>{analysis.checks.length}개 항목 확인</h2></div></div>
                    <div className="check-legend" aria-label="확인 상태 안내">
                      <span className="verified"><Check size={11} />확인 완료</span>
                      <span className="warning"><AlertTriangle size={11} />위험·불일치</span>
                      <span className="needs_review"><CircleHelp size={11} />확인 불가</span>
                      <span className="user_confirmed"><PenLine size={11} />사용자 입력</span>
                    </div>
                    <div className="check-list">
                      {analysis.checks.map((check) => {
                        const userConfirmed = check.sources.some((source) => source.corrected);
                        const visualStatus = userConfirmed ? "user_confirmed" : check.status;
                        const statusLabel = userConfirmed ? "사용자 입력" : check.status === "verified" ? "확인 완료" : check.status === "warning" ? "위험·불일치" : "확인 불가";
                        return (
                          <div key={check.label}>
                            <span className={visualStatus}>{visualStatus === "verified" ? <Check size={14} /> : visualStatus === "user_confirmed" ? <PenLine size={14} /> : visualStatus === "needs_review" ? <CircleHelp size={14} /> : <AlertTriangle size={14} />}</span>
                            <div className="check-copy">
                              <div className="check-title"><strong>{check.label}</strong><em className={visualStatus}>{statusLabel}</em></div>
                              <small>{check.detail}</small>
                              <EvidenceList sources={check.sources} />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </article>

                  <article className="source-card">
                    <ShieldCheck size={22} />
                    <div><strong>{hasMarketData ? "공식 데이터로 확인했어요" : "업로드 문서와 공식 주소를 확인했어요"}</strong><p>{hasMarketData ? `등기부등본 · 건축HUB · 국토교통부 실거래가${analysis.deposit_market.status === "available" ? " · 전월세 ML 기준" : ""}${analysis.mode === "contract_review" ? " · 임대차계약서" : ""}` : `등기부등본 · 건축물대장${analysis.mode === "contract_review" ? " · 임대차계약서" : ""} · ${analysis.market_data.status === "unavailable" ? "비교 거래 부족" : "실거래가 미연동"}`}</p></div>
                  </article>
                </aside>
              </div>

              <div className="disclaimer"><Info size={15} /> {analysis.disclaimer}</div>
            </section>
          )}
        </div>
      </main>
    </div>
  );
}
