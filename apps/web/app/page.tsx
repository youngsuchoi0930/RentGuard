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
    estimated_value: number | null;
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
  }>;
  checks: Array<{
    label: string;
    status: "verified" | "warning" | "needs_review";
    detail: string;
  }>;
  actions: string[];
  market_data: {
    status: "not_connected" | "available";
    message: string;
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
  disclaimer: string;
};

const DOCUMENTS: Array<{ key: DocKey; label: string; hint: string }> = [
  { key: "registry", label: "등기부등본", hint: "소유권·근저당 확인" },
  { key: "building_ledger", label: "건축물대장", hint: "용도·위반 여부 확인" },
  { key: "lease_contract", label: "임대차계약서", hint: "계약자·보증금 확인" },
];

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

export default function HomePage() {
  const [stage, setStage] = useState<Stage>("form");
  const [mobileMenu, setMobileMenu] = useState(false);
  const [address, setAddress] = useState("");
  const [deposit, setDeposit] = useState("");
  const [monthlyRent, setMonthlyRent] = useState("");
  const [files, setFiles] = useState<Partial<Record<DocKey, File>>>({});
  const [progress, setProgress] = useState(0);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [expandedSignal, setExpandedSignal] = useState<string | null>(null);

  const uploadedCount = Object.keys(files).length;
  const canAnalyze = address.trim().length >= 5 && parseMoney(deposit) > 0 && uploadedCount === DOCUMENTS.length;
  const hasMarketData = analysis?.market_data.status === "available" && analysis.facts.estimated_value !== null;
  const steps = useMemo(() => [
    { label: "계약 정보", done: stage !== "form", current: stage === "form" },
    { label: "서류 분석", done: stage === "result", current: stage === "analyzing" },
    { label: "위험 리포트", done: false, current: stage === "result" },
  ], [stage]);

  useEffect(() => {
    if (stage !== "analyzing") return;
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

  const runAnalysis = async () => {
    if (!canAnalyze) {
      setError("주소와 보증금을 입력하고 PDF 문서 3개를 모두 올려주세요.");
      return;
    }

    setError(null);
    setAnalysis(null);
    setProgress(4);
    setElapsedSeconds(0);
    setStage("analyzing");

    const formData = new FormData();
    formData.set("address", address);
    formData.set("deposit", String(parseMoney(deposit)));
    formData.set("monthly_rent", String(parseMoney(monthlyRent)));
    Object.entries(files).forEach(([key, file]) => file && formData.set(key, file));

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/analyses`, {
        method: "POST",
        body: formData,
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
      const message = cause instanceof Error && cause.message !== "Failed to fetch"
        ? cause.message
        : "분석 API에 연결할 수 없습니다. API 서버가 실행 중인지 확인해주세요.";
      setError(message);
      setProgress(0);
      setStage("form");
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
                <div className="eyebrow"><Sparkles size={15} /> AI 계약서류 교차검증</div>
                <h1>계약하기 전,<br /><em>서류 속 위험</em>을 먼저 확인하세요.</h1>
                <p>주소와 계약 조건, 서류 3가지만 준비하면 복잡한 권리관계를 한눈에 정리해드려요.</p>
              </div>

              <div className="form-grid">
                <div className="form-card">
                  <div className="card-title"><span>1</span><div><h2>계약 정보를 알려주세요</h2><p>계약서에 적힌 내용을 그대로 입력해주세요.</p></div></div>
                  <label className="field-label" htmlFor="address">집 주소</label>
                  <div className="input-shell"><MapPin size={19} /><input id="address" placeholder="계약서의 도로명주소" value={address} onChange={(e) => setAddress(e.target.value)} /><button>주소 찾기</button></div>
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
                    <Info size={16} /> {parseMoney(deposit) > 0 ? `${money(parseMoney(deposit))} 보증부 계약으로 분석합니다.` : "보증금을 입력하면 문서 추출값과 비교합니다."}
                  </div>
                </div>

                <div className="form-card documents-card">
                  <div className="card-title"><span>2</span><div><h2>계약 서류를 올려주세요</h2><p>PDF · 파일당 최대 20MB</p></div><div className="count-badge">{uploadedCount}/3</div></div>
                  <div className="document-list">
                    {DOCUMENTS.map((doc) => {
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
                  <div className="sample-note"><UploadCloud size={18} /><div><strong>PDF 세 종류가 모두 필요해요</strong><span>목업 결과 없이 업로드한 문서만 분석합니다.</span></div></div>
                </div>
              </div>

              <div className="form-footer">
                <div><ShieldCheck size={18} /><span>원본 파일은 분석 후 즉시 삭제됩니다.</span></div>
                <button className="primary-button" disabled={!canAnalyze} onClick={runAnalysis}>계약 위험 분석하기 <ArrowRight size={19} /></button>
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
              <p>문서에서 핵심 정보를 읽고 서로 대조합니다. 스캔 문서는 몇 분 걸릴 수 있어요.</p>
              <div className="progress-shell"><div style={{ width: `${progress}%` }} /></div>
              <strong className="progress-number">{progress}% · {elapsedSeconds}초 경과</strong>
              <div className="analysis-steps">
                <span className={progress > 18 ? "done" : "active"}><CheckCircle2 /> 문서 분류</span>
                <span className={progress > 45 ? "done" : progress > 18 ? "active" : ""}><FileText /> 핵심정보 추출</span>
                <span className={progress > 70 ? "done" : progress > 45 ? "active" : ""}><Building2 /> 문서 교차검증</span>
                <span className={progress > 90 ? "active" : ""}><ShieldCheck /> 위험도 계산</span>
              </div>
            </section>
          )}

          {stage === "result" && analysis && (
            <section className="result-stage">
              <div className="result-header">
                <button className="back-button" onClick={() => setStage("form")}><ArrowLeft size={17} /> 새 계약 분석</button>
                <div>
                  <div className="eyebrow"><CheckCircle2 size={15} /> {analysis.status === "complete" ? "분석 완료" : analysis.status === "partial" ? "문서 분석 완료 · 시세 연동 전" : "확인 필요한 항목 있음"} · {analysis.analysis_id.slice(0, 8)}</div>
                  <h1>{address}</h1>
                  <p>보증금 {money(analysis.facts.deposit)} · 월세 {money(parseMoney(monthlyRent))}</p>
                </div>
                <button className="outline-button" onClick={runAnalysis}><RefreshCw size={16} /> 다시 분석</button>
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
                      <span className="danger-pill"><AlertTriangle size={15} /> 문서 위험도 {analysis.grade}</span>
                      <h2>{analysis.headline}</h2>
                      <p>{analysis.summary}</p>
                    </div>
                  </article>

                  {analysis.ai_explanation.status === "generated" && analysis.ai_explanation.overview && (
                    <article className="ai-explanation-card">
                      <div className="ai-explanation-head">
                        <div><Sparkles size={17} /><span>Gemini 쉬운 설명</span></div>
                        <small>개인정보 제외 후 생성</small>
                      </div>
                      <h2>분석 결과를 쉽게 풀어봤어요</h2>
                      <p>{analysis.ai_explanation.overview}</p>
                      <div className="ai-explanation-points">
                        {analysis.ai_explanation.caution && <div><strong>왜 확인해야 하나요?</strong><span>{analysis.ai_explanation.caution}</span></div>}
                        {analysis.ai_explanation.limitation && <div><strong>어디까지 참고해야 하나요?</strong><span>{analysis.ai_explanation.limitation}</span></div>}
                      </div>
                      {analysis.ai_explanation.privacy_note && <small className="ai-privacy"><LockKeyhole size={13} /> {analysis.ai_explanation.privacy_note}</small>}
                    </article>
                  )}

                  <article className="metric-card">
                    <div className="section-heading"><div><span>핵심 수치</span><h2>돈의 흐름을 먼저 확인했어요</h2></div><button><Info size={16} /> 산정 기준</button></div>
                    <div className="metrics">
                      <div><span>예상 주택가액</span><strong>{money(analysis.facts.estimated_value)}</strong><small>{hasMarketData ? `${analysis.facts.recent_transactions ?? 0}건 실거래 기준` : "공공 실거래가 연동 전"}</small></div>
                      <div><span>근저당 채권최고액</span><strong className="danger-text">{money(analysis.facts.mortgage_amount)}</strong><small>등기부등본 추출</small></div>
                      <div><span>입력 보증금</span><strong>{money(analysis.facts.deposit)}</strong><small>계약서 추출값과 교차검증</small></div>
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
                  </article>

                  <article className="signals-card">
                    <div className="section-heading"><div><span>발견된 위험 신호</span><h2>왜 주의해야 하는지 알려드려요</h2></div><div className="signal-count">{analysis.signals.length}개 발견</div></div>
                    <div className="signal-list">
                      {analysis.signals.map((signal) => {
                        const open = expandedSignal === signal.id;
                        return (
                          <button className={`signal-row ${signal.severity} ${open ? "open" : ""}`} key={signal.id} onClick={() => setExpandedSignal(open ? null : signal.id)}>
                            <span className="signal-icon">{signal.severity === "notice" ? <Info size={19} /> : <AlertTriangle size={19} />}</span>
                            <span className="signal-copy"><strong>{signal.title}</strong><small>{signal.evidence}</small>{open && <p>{signal.description}</p>}</span>
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
                    <div className="section-heading"><div><span>서류 교차검증</span><h2>{analysis.checks.length}개 항목 확인</h2></div></div>
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
                    <div><strong>{hasMarketData ? "공식 데이터로 확인했어요" : "업로드한 문서 3종으로 확인했어요"}</strong><p>{hasMarketData ? "등기부등본 · 건축물대장 · 국토교통부 실거래가" : "등기부등본 · 건축물대장 · 임대차계약서 · 실거래가 미연동"}</p></div>
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
