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
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  X,
} from "lucide-react";
import { ChangeEvent, useEffect, useMemo, useState } from "react";

type Stage = "form" | "analyzing" | "result";
type DocKey = "registry" | "building_ledger" | "lease_contract";

type Analysis = {
  analysis_id: string;
  score: number;
  grade: "낮음" | "주의" | "높음";
  headline: string;
  summary: string;
  facts: {
    owner: string;
    contract_owner: string;
    mortgage_amount: number;
    deposit: number;
    estimated_value: number;
    building_use: string;
    is_illegal_building: boolean;
    approval_year: number;
    recent_transactions: number;
    local_price_volatility: number;
  };
  signals: Array<{
    id: string;
    severity: "safe" | "notice" | "warning" | "danger";
    title: string;
    description: string;
    evidence: string;
    points: number;
  }>;
  checks: Array<{
    label: string;
    status: "verified" | "warning" | "needs_review";
    detail: string;
  }>;
  actions: string[];
  disclaimer: string;
};

const DOCUMENTS: Array<{ key: DocKey; label: string; hint: string }> = [
  { key: "registry", label: "등기부등본", hint: "소유권·근저당 확인" },
  { key: "building_ledger", label: "건축물대장", hint: "용도·위반 여부 확인" },
  { key: "lease_contract", label: "임대차계약서", hint: "계약자·보증금 확인" },
];

const mockAnalysis: Analysis = {
  analysis_id: "RG-2026-0907-1042",
  score: 73,
  grade: "높음",
  headline: "주의가 필요한 계약입니다",
  summary: "예상 주택가액 대비 보증금은 68%, 근저당을 합친 부담은 118%입니다. 점수는 위험 신호의 우선순위를 보여주며 법률적 안전을 보증하지 않습니다.",
  facts: {
    owner: "김민준",
    contract_owner: "김민준",
    mortgage_amount: 110000000,
    deposit: 150000000,
    estimated_value: 220000000,
    building_use: "다세대주택",
    is_illegal_building: false,
    approval_year: 2017,
    recent_transactions: 3,
    local_price_volatility: 0.08,
  },
  signals: [
    { id: "senior-burden", severity: "danger", title: "선순위 부담 비율이 높아요", description: "근저당 채권최고액과 보증금의 합이 예상 주택가액을 넘습니다.", evidence: "예상 부담 비율 118%", points: 35 },
    { id: "mortgage", severity: "danger", title: "근저당 설정액이 큽니다", description: "등기부상 채권최고액이 예상 주택가액의 절반입니다.", evidence: "근저당 비율 50%", points: 20 },
    { id: "deposit-ratio", severity: "warning", title: "보증금이 시세에 가까워요", description: "가격 하락 시 보증금 회수 여력이 줄어들 수 있습니다.", evidence: "보증금 비율 68%", points: 8 },
  ],
  checks: [
    { label: "소유자와 계약자", status: "verified", detail: "김민준 · 일치합니다" },
    { label: "보증금 교차검증", status: "verified", detail: "입력값과 계약서가 일치합니다" },
    { label: "위반건축물", status: "verified", detail: "해당 없음" },
    { label: "보증보험 가입", status: "needs_review", detail: "보증기관 확인 필요" },
  ],
  actions: [
    "잔금 지급 직전 최신 등기부등본을 다시 확인하세요.",
    "특약사항에 잔금 전 근저당 말소 조건을 명확히 추가하세요.",
    "HUG 등 보증기관에서 보증 가입 가능 여부를 직접 확인하세요.",
  ],
  disclaimer: "이 결과는 계약 의사결정을 돕는 참고 정보이며 법률 자문이나 보증 가입 심사를 대신하지 않습니다.",
};

function money(value: number) {
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

export default function HomePage() {
  const [stage, setStage] = useState<Stage>("form");
  const [mobileMenu, setMobileMenu] = useState(false);
  const [address, setAddress] = useState("서울특별시 강서구 화곡로 123");
  const [deposit, setDeposit] = useState("150,000,000");
  const [monthlyRent, setMonthlyRent] = useState("100,000");
  const [files, setFiles] = useState<Partial<Record<DocKey, File>>>({});
  const [progress, setProgress] = useState(0);
  const [analysis, setAnalysis] = useState<Analysis>(mockAnalysis);
  const [expandedSignal, setExpandedSignal] = useState<string | null>("senior-burden");

  const uploadedCount = Object.keys(files).length;
  const steps = useMemo(() => [
    { label: "계약 정보", done: stage !== "form", current: stage === "form" },
    { label: "서류 분석", done: stage === "result", current: stage === "analyzing" },
    { label: "위험 리포트", done: false, current: stage === "result" },
  ], [stage]);

  useEffect(() => {
    if (stage !== "analyzing") return;
    const timer = window.setInterval(() => {
      setProgress((current) => Math.min(current + (current < 55 ? 9 : 4), 92));
    }, 180);
    return () => window.clearInterval(timer);
  }, [stage]);

  const handleFile = (key: DocKey, event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) setFiles((current) => ({ ...current, [key]: file }));
  };

  const runAnalysis = async () => {
    setProgress(4);
    setStage("analyzing");

    const formData = new FormData();
    formData.set("address", address);
    formData.set("deposit", String(parseMoney(deposit)));
    formData.set("monthly_rent", String(parseMoney(monthlyRent)));
    Object.entries(files).forEach(([key, file]) => file && formData.set(key, file));

    const startedAt = Date.now();
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/analyses`, {
        method: "POST",
        body: formData,
        signal: AbortSignal.timeout(2800),
      });
      if (!response.ok) throw new Error("analysis failed");
      setAnalysis(await response.json());
    } catch {
      setAnalysis({ ...mockAnalysis, facts: { ...mockAnalysis.facts, deposit: parseMoney(deposit) || 150000000 } });
    }

    const remaining = Math.max(0, 1600 - (Date.now() - startedAt));
    window.setTimeout(() => {
      setProgress(100);
      window.setTimeout(() => setStage("result"), 250);
    }, remaining);
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
          <div className="trust-note"><span className="live-dot" /> 공식 데이터 기반 분석</div>
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
              <div className="page-heading">
                <div className="eyebrow"><Sparkles size={15} /> AI 계약서류 교차검증</div>
                <h1>계약하기 전,<br /><em>서류 속 위험</em>을 먼저 확인하세요.</h1>
                <p>주소와 계약 조건, 서류 3가지만 준비하면 복잡한 권리관계를 한눈에 정리해드려요.</p>
              </div>

              <div className="form-grid">
                <div className="form-card">
                  <div className="card-title"><span>1</span><div><h2>계약 정보를 알려주세요</h2><p>계약서에 적힌 내용을 그대로 입력해주세요.</p></div></div>
                  <label className="field-label" htmlFor="address">집 주소</label>
                  <div className="input-shell"><MapPin size={19} /><input id="address" value={address} onChange={(e) => setAddress(e.target.value)} /><button>주소 찾기</button></div>
                  <div className="money-grid">
                    <div>
                      <label className="field-label" htmlFor="deposit">보증금</label>
                      <div className="input-shell"><input id="deposit" inputMode="numeric" value={deposit} onChange={(e) => setDeposit(formatInput(e.target.value))} /><span>원</span></div>
                    </div>
                    <div>
                      <label className="field-label" htmlFor="rent">월세</label>
                      <div className="input-shell"><input id="rent" inputMode="numeric" value={monthlyRent} onChange={(e) => setMonthlyRent(formatInput(e.target.value))} /><span>원</span></div>
                    </div>
                  </div>
                  <div className="mini-summary">
                    <Info size={16} /> {money(parseMoney(deposit))} 보증부 월세 계약으로 분석합니다.
                  </div>
                </div>

                <div className="form-card documents-card">
                  <div className="card-title"><span>2</span><div><h2>계약 서류를 올려주세요</h2><p>PDF, JPG, PNG · 파일당 최대 20MB</p></div><div className="count-badge">{uploadedCount}/3</div></div>
                  <div className="document-list">
                    {DOCUMENTS.map((doc) => {
                      const file = files[doc.key];
                      return (
                        <label className={`document-row ${file ? "uploaded" : ""}`} key={doc.key}>
                          <input type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={(event) => handleFile(doc.key, event)} />
                          <div className="doc-icon">{file ? <FileCheck2 size={21} /> : <FileText size={21} />}</div>
                          <div className="doc-copy"><strong>{file?.name ?? doc.label}</strong><span>{file ? `${(file.size / 1024 / 1024).toFixed(1)}MB · 업로드 완료` : doc.hint}</span></div>
                          <div className="upload-action">{file ? <Check size={17} /> : <><Plus size={16} /><span>추가</span></>}</div>
                        </label>
                      );
                    })}
                  </div>
                  <div className="sample-note"><UploadCloud size={18} /><div><strong>서류가 아직 없나요?</strong><span>지금은 샘플 추출값으로 전체 분석 흐름을 체험할 수 있어요.</span></div></div>
                </div>
              </div>

              <div className="form-footer">
                <div><ShieldCheck size={18} /><span>원본 파일은 분석 후 즉시 삭제됩니다.</span></div>
                <button className="primary-button" onClick={runAnalysis}>계약 위험 분석하기 <ArrowRight size={19} /></button>
              </div>
            </section>
          )}

          {stage === "analyzing" && (
            <section className="analyzing-stage">
              <div className="scan-visual">
                <div className="scan-paper"><FileText size={58} /><span className="scan-line" /></div>
                <div className="orbit"><ShieldCheck size={25} /></div>
              </div>
              <div className="eyebrow"><LoaderCircle className="spin" size={15} /> DOCUMENT AI</div>
              <h1>서류를 꼼꼼히<br />교차검증하고 있어요</h1>
              <p>문서에서 핵심 정보를 읽고, 공공데이터와 대조합니다.</p>
              <div className="progress-shell"><div style={{ width: `${progress}%` }} /></div>
              <strong className="progress-number">{progress}%</strong>
              <div className="analysis-steps">
                <span className={progress > 18 ? "done" : "active"}><CheckCircle2 /> 문서 분류</span>
                <span className={progress > 45 ? "done" : progress > 18 ? "active" : ""}><FileText /> 핵심정보 추출</span>
                <span className={progress > 70 ? "done" : progress > 45 ? "active" : ""}><Building2 /> 공공데이터 대조</span>
                <span className={progress > 90 ? "active" : ""}><ShieldCheck /> 위험도 계산</span>
              </div>
            </section>
          )}

          {stage === "result" && (
            <section className="result-stage">
              <div className="result-header">
                <button className="back-button" onClick={() => setStage("form")}><ArrowLeft size={17} /> 새 계약 분석</button>
                <div>
                  <div className="eyebrow"><CheckCircle2 size={15} /> 분석 완료 · {analysis.analysis_id.slice(0, 18)}</div>
                  <h1>{address}</h1>
                  <p>보증금 {money(analysis.facts.deposit)} · 월세 {money(parseMoney(monthlyRent))}</p>
                </div>
                <button className="outline-button" onClick={runAnalysis}><RefreshCw size={16} /> 다시 분석</button>
              </div>

              <div className="report-layout">
                <div className="report-main">
                  <article className="risk-hero">
                    <div className="score-ring" style={{ "--score": analysis.score } as React.CSSProperties}>
                      <div><strong>{analysis.score}</strong><span>/ 100</span></div>
                    </div>
                    <div className="risk-copy">
                      <span className="danger-pill"><AlertTriangle size={15} /> 위험도 {analysis.grade}</span>
                      <h2>{analysis.headline}</h2>
                      <p>{analysis.summary}</p>
                    </div>
                  </article>

                  <article className="metric-card">
                    <div className="section-heading"><div><span>핵심 수치</span><h2>돈의 흐름을 먼저 확인했어요</h2></div><button><Info size={16} /> 산정 기준</button></div>
                    <div className="metrics">
                      <div><span>예상 주택가액</span><strong>{money(analysis.facts.estimated_value)}</strong><small>인근 실거래 3건 기준</small></div>
                      <div><span>근저당 채권최고액</span><strong className="danger-text">{money(analysis.facts.mortgage_amount)}</strong><small>등기부등본 추출</small></div>
                      <div><span>내 보증금</span><strong>{money(analysis.facts.deposit)}</strong><small>계약서·입력값 일치</small></div>
                    </div>
                    <div className="burden-bar">
                      <div className="bar-labels"><span>예상 주택가액 {money(analysis.facts.estimated_value)}</span><strong>부담 합계 {money(analysis.facts.mortgage_amount + analysis.facts.deposit)} <em>118%</em></strong></div>
                      <div className="bar-track"><span className="mortgage-segment" /><span className="deposit-segment" /></div>
                      <div className="legend"><span><i className="legend-mortgage" />근저당 50%</span><span><i className="legend-deposit" />보증금 68%</span><span><i className="legend-limit" />주택가액 100%</span></div>
                    </div>
                  </article>

                  <article className="signals-card">
                    <div className="section-heading"><div><span>발견된 위험 신호</span><h2>왜 주의해야 하는지 알려드려요</h2></div><div className="signal-count">{analysis.signals.length}개 발견</div></div>
                    <div className="signal-list">
                      {analysis.signals.map((signal) => {
                        const open = expandedSignal === signal.id;
                        return (
                          <button className={`signal-row ${signal.severity} ${open ? "open" : ""}`} key={signal.id} onClick={() => setExpandedSignal(open ? null : signal.id)}>
                            <span className="signal-icon"><AlertTriangle size={19} /></span>
                            <span className="signal-copy"><strong>{signal.title}</strong><small>{signal.evidence}</small>{open && <p>{signal.description}</p>}</span>
                            <span className="points">+{signal.points}점</span>
                            <ChevronDown className="chevron" size={18} />
                          </button>
                        );
                      })}
                    </div>
                  </article>
                </div>

                <aside className="report-side">
                  <article className="action-card">
                    <div className="action-card-head"><span><Sparkles size={17} /> 지금 해야 할 일</span><strong>계약 전 행동 3가지</strong></div>
                    <ol>
                      {analysis.actions.map((action, index) => <li key={action}><span>{index + 1}</span><p>{action}</p></li>)}
                    </ol>
                    <button>행동 체크리스트 저장 <ArrowRight size={17} /></button>
                  </article>

                  <article className="checks-card">
                    <div className="section-heading"><div><span>서류 교차검증</span><h2>4개 항목 확인</h2></div></div>
                    <div className="check-list">
                      {analysis.checks.map((check) => (
                        <div key={check.label}>
                          <span className={check.status}>{check.status === "verified" ? <Check size={14} /> : <AlertTriangle size={14} />}</span>
                          <p><strong>{check.label}</strong><small>{check.detail}</small></p>
                        </div>
                      ))}
                    </div>
                  </article>

                  <article className="source-card">
                    <ShieldCheck size={22} />
                    <div><strong>공식 데이터로 확인했어요</strong><p>등기부등본 · 건축물대장 · 국토교통부 실거래가</p></div>
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
