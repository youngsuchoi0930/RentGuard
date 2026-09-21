# RentGuard AI 개발 인수인계서

> 마지막 정리일: 2026-09-14  
> 기준 브랜치: `main`  
> 기준 커밋: `86dbee0` (`fix and fix`)  
> 목적: 다른 컴퓨터에서 저장소를 받은 뒤 기존 작업을 반복하지 않고 바로 개발을 이어가기 위한 문서

## 1. 프로젝트 한 줄 설명

RentGuard는 임대차 계약 전에 등기사항증명서·건축물대장·임대차계약서를 분석하고, 공공데이터와 교차검증하여 위험 신호·점수·행동 지침을 제공하는 서비스다.

현재 제공하는 분석 방식은 다음 두 가지다.

| 모드 | 필요한 입력 | 용도 |
|---|---|---|
| 사전점검 `precheck` | 주소, 예정 보증금·월세, 등기부등본, 건축물대장 | 계약서 작성 전 권리·시세·보증금 조건 점검 |
| 계약서 교차검증 `contract_review` | 사전점검 입력 + 임대차계약서 | 계약서와 등기·건축물대장·사용자 입력의 일치 여부 확인 |

## 2. 현재 구현 상태

| 영역 | 상태 | 현재 구현 내용 |
|---|---|---|
| 프로젝트 구조 | 완료 | Next.js 웹과 FastAPI API 분리 |
| 계약정보 입력 | 완료 | 주소 검색, 보증금·월세 입력 |
| 문서 업로드 | 완료 | 모드별 PDF 2종 또는 3종 업로드 |
| 추출값 확인·수정 | 완료 | 분석 전에 추출값 확인, 사용자 수정 및 수정 이력 보존 |
| PDF 텍스트 추출 | 완료 | 텍스트 레이어 우선 사용 |
| 이미지 OCR | 완료 v1 | 스캔 PDF는 PaddleOCR로 처리, Docker 런타임 지원 |
| 등기부 분석 | 완료 v1 | 주소, 현재 소유자, 근저당, 주요 권리, 순위·접수일·말소 여부 추출 |
| 건축물대장 분석 | 완료 v1 | 주소, 호수, 면적, 용도, 구조, 사용승인일 등 추출 |
| 임대차계약서 분석 | 완료 v1 | 임대인·임차인, 주소, 보증금, 월세 등 추출 |
| 문서 교차검증 | 완료 | 주소, 소유자↔임대인, 보증금·월세, 위반건축물 항목 대조 |
| 공공 주소 검색 | 완료 | 도로명주소 API로 주소·법정동 코드·지번 확인 |
| 건축HUB 연동 | 완료 | 공식 표제부 조회 및 업로드 문서와 대조 |
| 실거래가 연동 | 완료 | 최근 12개월 연립·다세대 매매 거래 조회 |
| 예상 주택가액 | 완료 v1 | 같은 법정동·유사 면적 거래의 ㎡당 중간가격과 25~75% 범위 사용 |
| 위험 엔진 | 완료 v2 | 근저당, 보증금, 합산 부담, 권리관계, 가격 변동성 규칙 |
| 보증금 ML | 완료 v2 | 서울 연립·다세대 전월세 신고자료 기반 p50·p95 예측 |
| Gemini 설명 | 완료 | 개인정보를 제외한 위험 범주만 전달해 쉬운 설명 생성 |
| 증거 추적 | 완료 | 문서·페이지·추출 방식·원문·신뢰도·사용자 수정 여부 표시 |
| 반응형 화면 | 완료 | 데스크톱·모바일 대응 |
| Docker | 완료 | 웹·API 이미지, API health check, 검증된 모델 포함 |
| 자동 테스트 | 완료 | API, 추출기, 교차검증, 공공데이터, ML 회귀 테스트 |
| DB·분석 기록 | 완료 v1 | SQLite 목록·상세·삭제, Docker volume 영속화, 개인정보 제거 |
| 사용자 피드백 | 완료 v1 | 피드백 저장·통계, 검수 대기/승인/제외, 승인 데이터 CSV·JSON 내보내기 |
| 공식자료 RAG | 미구현 | HUG·국토부 공식 가이드 검색/인용 계층 필요 |
| 실제 보증사고 모델 | 미구현 | 사고 결과가 라벨링된 데이터 없음 |
| 클라우드 배포 | 미구현 | 현재 로컬 Docker 실행까지 완료 |

## 3. 핵심 설계 결정

1. 위험 판단과 자연어 설명을 분리한다.
   - 규칙 엔진과 ML이 수치·신호를 만든다.
   - Gemini는 만들어진 결과를 설명할 뿐 점수나 사실을 바꾸지 않는다.
2. 모르는 값은 안전으로 간주하지 않는다.
   - 추출 또는 공식 확인이 불가능하면 `needs_review`로 표시한다.
3. 사용자 수정은 OCR 정답으로 위장하지 않는다.
   - 원래 추출값과 수정값을 별도로 남기고 결과 화면에 `사용자 입력`으로 표시한다.
4. 분석 결과에는 근거를 연결한다.
   - 위험 신호마다 문서, 페이지, 추출 원문, 방식과 신뢰도를 제공한다.
5. 같은 문서·입력은 외부 API의 일시적 장애와 관계없이 가능한 한 동일한 결과를 내야 한다.
   - 업로드 건축물대장의 면적·사용승인일을 분석 스냅샷의 우선값으로 사용한다.
   - 건축HUB는 누락값 보완 및 공식 교차검증에 사용한다.

## 4. 전체 분석 흐름

```text
주소·예정 계약조건 입력
        │
        ▼
PDF 업로드 및 문서 분류
        │
        ▼
텍스트 추출 ── 텍스트 없음/부족 ──▶ PaddleOCR
        │
        ▼
등기부·건축물대장·계약서 필드 구조화
        │
        ▼
사용자 추출값 확인 및 수정
        │
        ├──────────────┬────────────────┐
        ▼              ▼                ▼
도로명주소 API      건축HUB          국토부 실거래가
        └──────────────┴────────────────┘
                       │
                       ▼
문서 교차검증 + 규칙 위험 엔진 + 보증금 ML
                       │
                       ▼
점수·근거·확인 상태·행동 지침
                       │
                       ▼
개인정보 제외 구조만 Gemini에 전달해 쉬운 설명 생성
```

프론트엔드는 PDF를 곧바로 최종 판단에 사용하지 않는다.

1. `POST /api/v1/document-bundles/extract`로 문서를 추출한다.
2. 사용자가 추출값을 확인·수정한다.
3. `POST /api/v1/analyses/from-extractions`로 공공데이터 대조와 최종 위험 계산을 수행한다.

## 5. 지금까지 해결한 주요 버그와 오탐

| 문제 | 원인 | 적용한 해결책 | 결과 |
|---|---|---|---|
| 회전된 건축물대장 OCR 실패 | PDF 회전 메타데이터와 실제 페이지 방향 불일치 | 원본을 보존하고 실제 페이지 내용을 회전한 별도 PDF 생성 | 정방향 OCR 가능 |
| Docker OCR 실행 실패 | PaddleOCR에 필요한 OS 라이브러리 부족 | API 이미지에 `libgl1`, `libglib2.0-0`, `libgomp1` 추가 | Docker OCR 정상 실행 |
| OCR 실패가 일반 네트워크 오류처럼 표시 | 서버 OCR 오류와 브라우저 연결 오류를 구분하지 않음 | 구조화된 503 오류와 프론트 오류 메시지 분리 | 원인별 안내 가능 |
| OCR 중복 초기화와 동시 실행 불안정 | 요청마다 초기화하거나 추론이 겹칠 가능성 | 초기화 오류 캐시와 추론 직렬화 적용 | 반복 요청 안정성 개선 |
| 도로명주소·지번주소를 서로 다른 주소로 오탐 | 공백, 괄호, 행정동, 집합건물 표현 차이 | 주소 정규화 및 도로명/지번/호수 비교 규칙 개선 | 같은 부동산으로 정상 인식 |
| 입력 주소에 호수가 없으면 실거래 0건 | 건축HUB가 전유면적을 특정하지 못함 | 업로드 건축물대장의 전용면적을 실거래 비교의 fallback으로 사용 | 유사 면적 실거래 조회 복구 |
| 근저당 순위·접수일 오추출 | 이전 소유권 행의 날짜가 근저당 행으로 전파됨 | 같은 권리 행의 순위·날짜를 우선 묶도록 파서 수정 | 근저당 행 기준으로 정상 추출 |
| 근저당 근거가 긴 등기 원문 전체로 표시 | 권리 행 주변 텍스트 범위가 과도함 | 사용자용 설명과 핵심 금액 근거를 간결하게 표시 | 위험 설명 가독성 개선 |
| 건축HUB 성공/실패에 따라 보증금 예측 변동 | HUB 실패 시 사용승인일이 ML 입력에서 사라짐 | 업로드 문서의 면적·사용승인일을 우선 사용 | 동일 문서 결과 고정 |
| 일부 API 실패 중에도 모든 공식 데이터를 확인했다고 표시 | 실거래 성공 여부만으로 하단 문구 결정 | 건축HUB 상태까지 확인해 `일부 공식 데이터만 확인했어요` 표시 | 과장된 상태 안내 제거 |
| LLM 설명이 프론트에 보이지 않음 | 백엔드 결과와 프론트 표시 계층이 분리되어 있었음 | 결과 화면에 Gemini 설명 카드 연결 | 성공/실패 상태 모두 표시 |
| LLM 설명이 추상적임 | 위험 범주만 짧게 전달하여 구체성이 부족 | 확인 이유·한계·개인정보 제외 안내로 카드 구조 개선 | 보조 설명 역할 명확화 |

## 6. 실제 문서 기반 비공개 회귀 기준

실제 개인 문서는 저장소에 포함하지 않는다. 아래 값은 이름과 상세 주소를 제외한 `PRIVATE_CASE_001` 회귀 기준이다. 다른 컴퓨터로 원본을 옮긴 뒤 같은 케이스를 재실행할 때 사용한다.

| 항목 | 확인 기준 |
|---|---:|
| 전용면적 | 84.59㎡ |
| 건축물 주용도 | 연립주택 계열 |
| 사용승인일 | 1998-01-15 |
| 활성 근저당 채권최고액 | 231,000,000원 |
| 근저당 순위번호 | 7 |
| 근저당 접수일 | 2022-07-22 |
| 비교 매매 거래 | 51건 |
| 예상 주택가액 | 341,000,000원 |
| 예상가 중간 범위 | 299,000,000~382,000,000원 |
| 최근 가격 변동성 | 약 23.8% |
| 입력 보증금 | 30,000,000원 |
| 입력 월세 | 1,300,000원 |
| 보증금/예상가 | 약 9% |
| 근저당+보증금/예상가 | 약 77% |
| 위험점수 | 24점 (`근저당 +20`, `변동성 +4`) |
| 보증금 ML p50 | 61,700,000원 |
| 보증금 ML p95 | 214,800,000원 |

이 케이스에서 소유자 이름과 전체 주소는 이 문서나 Git에 기록하지 않는다. 원문을 직접 확인할 때만 비공개 로컬 파일을 사용한다.

## 7. ML 학습 상태와 데이터 사용 원칙

### 현재 모델

| 항목 | 값 |
|---|---|
| 파일 | `models/deposit-quantile-v2.joblib` |
| manifest | `models/deposit-quantile-v2.manifest.json` |
| 스키마 | `deposit-quantile-model-2.0` |
| 학습 데이터 기준월 | 2026-05 |
| 최종 홀드아웃 | 2026-06~2026-08 |
| 모델 파일 무결성 | manifest SHA-256 검증 |
| 학습 자료 | 국토교통부 서울 연립·다세대 전월세 신고자료 |

### 중요한 구분

- 개인 등기부와 건축물대장은 모델을 재학습하는 데 사용하지 않았다.
- 개인 문서는 OCR·파싱·교차검증·위험 계산·회귀 확인용 입력으로만 사용했다.
- 현재 모델에 개인 이름, 정확한 주소, OCR 원문, 분석 ID, 규칙 점수는 들어가지 않는다.
- 합성 데이터는 파이프라인과 희귀 조건 확인용이며 실제 사고 정확도 평가에 사용하지 않는다.
- 보증금 ML은 법적 안전이나 사기를 판정하지 않고 유사 계약 대비 통계적 범위만 제공한다.

### 현재 보증금 모델 지표

| 지표 | v2 |
|---|---:|
| 홀드아웃 p50 평균 절대오차 | 2,947만원 |
| 홀드아웃 p50 중앙 절대비율오차 | 13.93% |
| 홀드아웃 p95 포함률 | 95.03% |
| 합성 이상 조건 탐지율 | 75.90% |

## 8. API와 외부 연동

### 주요 API

| 엔드포인트 | 기능 |
|---|---|
| `GET /health` | API 및 보증금 모델 상태 확인 |
| `GET /api/v1/addresses/search` | 도로명주소 검색 |
| `POST /api/v1/documents/registry/extract` | 등기부 추출 |
| `POST /api/v1/documents/building-ledger/extract` | 건축물대장 추출 |
| `POST /api/v1/documents/lease-contract/extract` | 임대차계약서 추출 |
| `POST /api/v1/document-bundles/extract` | 모드별 문서 일괄 추출과 1차 교차검증 |
| `POST /api/v1/analyses` | PDF 업로드부터 최종 분석까지 한 번에 실행 |
| `POST /api/v1/analyses/from-extractions` | 사용자 확인·수정값으로 최종 분석 |
| `POST /api/v1/ml/dataset-rows/preview` | 저장 없이 비식별 ML 행 미리보기 |
| `GET /api/v1/analysis-history` | 비식별 분석 기록 목록 |
| `GET /api/v1/analysis-history/{analysis_id}` | 분석 기록 상세 |
| `DELETE /api/v1/analysis-history/{analysis_id}` | 분석 기록 삭제 |
| `GET /api/v1/analysis-history/{analysis_id}/feedback` | 분석별 비식별 피드백 조회 |
| `POST /api/v1/analysis-history/{analysis_id}/feedback` | 항목별 피드백 저장·갱신 |
| `GET /api/v1/feedback` | 전체 비식별 피드백 통계·필터 목록 |
| `PATCH /api/v1/feedback/{feedback_id}/review` | 피드백 검수 상태 변경 |
| `GET /api/v1/feedback/export?format=csv|json` | 승인 피드백만 비식별 학습 데이터로 내보내기 |

Swagger는 API 실행 후 `http://localhost:8000/docs`에서 확인한다.

### 필요한 환경변수 이름

값은 이 문서와 Git에 기록하지 않는다. 다른 컴퓨터에서 `.env.example`을 복사해 `.env`를 만들고 직접 입력한다.

| 변수 | 용도 |
|---|---|
| `GEMINI_API_KEY` | Gemini 쉬운 설명 |
| `GEMINI_MODEL` | Gemini 모델 지정, 기본값 `gemini-3.5-flash-lite` |
| `GEMINI_TIMEOUT_SECONDS` | Gemini 호출 제한 시간 |
| `JUSO_CONFIRM_KEY` | 도로명주소 검색 |
| `DATA_GO_KR_SERVICE_KEY` | 건축HUB 및 국토교통부 실거래가 |
| `PUBLIC_API_TIMEOUT_SECONDS` | 공공 API 제한 시간 |
| `PUBLIC_MARKET_MONTHS` | 실거래 비교 기간 |
| `REQUIRE_DEPOSIT_MODEL` | 보증금 모델 필수 여부 |
| `ANALYSIS_DB_PATH` | 선택적 SQLite 경로, 미설정 시 `data/rentguard.db` |

공공데이터포털 키 하나를 사용하더라도 건축HUB와 매매·전월세 서비스는 각각 활용신청 및 승인 상태를 확인해야 한다.

## 9. 새 컴퓨터에서 시작하는 순서

### Git 확인

```powershell
git pull
git status
git log -3 --oneline
```

기준 커밋 `86dbee0` 이후의 커밋이 있다면 최신 커밋을 우선한다.

### Docker 실행

저장소 루트에서:

```powershell
docker compose up -d --build
docker compose ps
```

확인 주소:

- 웹: `http://localhost:3000`
- API 문서: `http://localhost:8000/docs`
- 상태: `http://localhost:8000/health`

로그 확인:

```powershell
docker compose logs --tail 200 api
docker compose logs --tail 100 web
```

### 로컬 API 개발 환경

Python 3.12를 사용한다. Python 3.14는 현재 PaddlePaddle OCR 의존성과 맞지 않는다.

```powershell
cd apps/api
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

### 로컬 프론트 개발 환경

저장소 루트에서:

```powershell
corepack enable
corepack prepare pnpm@10.15.1 --activate
pnpm install --frozen-lockfile
pnpm dev:web
```

## 10. 테스트와 검증 명령

### 전체 API 테스트

```powershell
cd apps/api
.venv\Scripts\python -m pytest -q
```

분석 기록과 사용자 피드백 검수·내보내기 기능 추가 후 로컬 검증 결과는 `83 passed, 1 skipped`였다. `skipped` 항목은 기본 실행에서 제외한 OCR 전용 테스트다.

### 핵심 회귀 테스트

```powershell
cd apps/api
.venv\Scripts\python -m pytest tests/test_deposit_predictor.py tests/test_analysis_service.py -q
```

마지막 결과는 `12 passed`였다.

### OCR 테스트

```powershell
cd apps/api
$env:RUN_OCR_TESTS = "1"
.venv\Scripts\python -m pytest -q -m ocr
```

최초 실행은 한국어 OCR 모델 다운로드로 오래 걸릴 수 있다.

### 프론트 검증

```powershell
cd apps/web
npm run lint
npm run build
```

마지막 검증에서는 ESLint와 Next.js 프로덕션 빌드가 모두 통과했다.

## 11. 주요 파일 안내

| 경로 | 역할 |
|---|---|
| `apps/web/app/page.tsx` | 입력, 추출값 확인, 분석 진행, 결과 리포트 UI |
| `apps/api/app/main.py` | FastAPI 엔드포인트와 전체 실행 흐름 |
| `apps/api/app/services/pdf_extractor.py` | PDF 텍스트 및 OCR 처리 |
| `apps/api/app/services/registry_parser.py` | 등기부 소유권·근저당·권리 파싱 |
| `apps/api/app/services/building_parser.py` | 건축물대장 파싱 |
| `apps/api/app/services/lease_parser.py` | 임대차계약서 파싱 |
| `apps/api/app/services/cross_checker.py` | 문서 간 주소·계약정보 교차검증 |
| `apps/api/app/services/public_data.py` | 주소, 건축HUB, 매매 실거래가 연동 |
| `apps/api/app/services/analysis_service.py` | 공공데이터와 추출값을 최종 분석 결과로 조립 |
| `apps/api/app/services/analysis_history.py` | 비식별 분석 기록의 SQLite 저장·조회·삭제 |
| `apps/api/app/services/deposit_predictor.py` | 보증금 p50·p95 모델 로딩과 예측 |
| `apps/api/app/risk_engine.py` | 재현 가능한 규칙 기반 위험점수 |
| `apps/api/app/services/gemini_explainer.py` | 개인정보 제외 Gemini 설명 |
| `models/` | 검증된 보증금 모델과 manifest |
| `scripts/` | 데이터 수집, 합성 데이터, 모델 학습, PDF 평가 도구 |
| `output/pdf/rentguard-fixtures/` | Git에 포함 가능한 합성 테스트 PDF와 정답 |
| `docs/sample-data-guide.md` | 실제 문서 확보·익명화 절차 |
| `docs/ml-dataset-v1.md` | ML 특성·라벨·분할·지표 정의 |
| `docs/ARCHITECTURE.md` | 판단/설명 분리 아키텍처 |

## 12. 개인정보와 보안 원칙

- `.env`, `.env.local`, `local-fixtures/`는 Git에 올리지 않는다.
- 실제 등기부·건축물대장·계약서는 저장소 밖에서 관리한다.
- 원본 문서를 Git 테스트 fixture로 복사하지 않는다.
- 공유 가능한 테스트는 합성 문서 또는 육안 검증을 마친 익명화 사본만 사용한다.
- Gemini에는 PDF, 주소, 이름, 금액, 증거 원문을 전송하지 않는다.
- 업로드 원본은 현재 분석 요청 동안만 사용하며 분석 기록 DB에 저장하지 않는다.
- 사용자 피드백은 자유문장을 받지 않고 판정·수정 금액만 저장해 개인정보 유입을 제한한다.
- 모델 파일은 업로드 파일을 받지 않고 저장소가 제공한 manifest 검증 모델만 로드한다.

## 13. 현재 남아 있는 한계

| 한계 | 현재 처리 방식 |
|---|---|
| 건축HUB 표제부가 위반건축물 여부를 항상 제공하지 않음 | `확인 불가`로 표시하고 업로드 원문·공식 사이트 확인 안내 |
| HUG 보증 가입 가능 여부 자동 판정 미지원 | 보증기관에 직접 확인하도록 행동 지침 제공 |
| 공공 API 일시 장애 | 문서 fallback을 사용하되 공식 확인 상태는 별도로 표시 |
| 손글씨 계약서 정확도 데이터 부족 | 추출 실패를 `needs_review`로 보내고 사용자 수정 허용 |
| 일부 등기부 레이아웃만 실제 검증 | 의미 표식 중심 파싱과 합성 회귀 테스트 사용, 실제 익명화 사례 확대 필요 |
| 시세 모델 범위 제한 | 현재 연립·다세대 매매 실거래 중심, 표본 부족 시 계산 보류 |
| 보증금 ML 지역·유형 제한 | 서울 연립·다세대 범위 밖은 `out_of_scope` |
| 실제 사기·보증사고 예측 모델 없음 | 법적 안전 판정이 아닌 규칙·시장 이상 신호로만 제공 |
| 클라우드 운영 관측 없음 | 로컬 health check와 Docker 로그만 사용 |

## 14. 다음 개발 계획

| 우선순위 | 작업 | 완료 기준 |
|---|---|---|
| P0 | 실제 익명화 회귀 사례 확대 | 다양한 등기부·건축물대장·계약서 형식에서 필드별 정확도 측정 |
| P0 | 손글씨 계약서 OCR 평가 | 손글씨·도장·특약이 있는 문서의 보증금·월세·임대인 재현율 확인 |
| P0 | 공공 API 장애 스냅샷 테스트 확대 | 건축HUB 성공·실패·타임아웃에도 같은 문서의 핵심 계산이 일관됨 |
| P0 | 위험 엔진 기준 문서화 | 각 점수·상한·행동 지침의 정책 근거와 변경 이력 관리 |
| P1 | 기록 보관 정책·동의 UI | 보관 기간 선택, 전체 삭제, 저장 동의와 정책 표시 |
| P1 | 공식자료 RAG | HUG·국토부 공식 출처를 붙인 설명 제공 |
| P1 | 사용자 피드백 품질 규칙 | 승인 전 필수 확인 조건과 최소 표본 기준 정의 |
| P1 | 실제 라벨 평가 세트 | 정상·이상·확인된 위험 사례를 사람 검수 후 분리 보관 |
| P2 | 주택유형·지역 확장 | 아파트·오피스텔·다가구 및 서울 외 지역 모델 분리 |
| P2 | 클라우드 배포·관측 | HTTPS 공개 URL, CI/CD, 오류 추적, 비밀 관리, 헬스 모니터링 |
| P2 | 대회/발표 자료 | 3분 시연, 성과지표, 아키텍처, 개인정보 보호 설명 완성 |

## 15. 다음 작업자가 가장 먼저 할 일

1. `git pull` 후 이 문서의 기준 커밋보다 최신인지 확인한다.
2. `.env`와 비공개 문서가 새 컴퓨터에 준비됐는지 확인한다.
3. `docker compose up -d --build`를 실행한다.
4. `/health`에서 API, 분석 기록 DB와 `deposit-quantile-model-2.0`이 `ready/verified`인지 확인한다.
5. 합성 PDF로 빠른 분석을 수행한다.
6. 비공개 `PRIVATE_CASE_001`을 실행해 6절의 기준값과 비교한다.
7. 차이가 있으면 코드를 바로 수정하기 전에 OCR 추출값, 공공 API 응답 상태, ML 입력 피처를 각각 분리해 원인을 찾는다.

## 16. 관련 문서

- 프로젝트 실행과 API: `README.md`
- 아키텍처: `docs/ARCHITECTURE.md`
- 실제 문서 확보와 익명화: `docs/sample-data-guide.md`
- ML 데이터 정책과 지표: `docs/ml-dataset-v1.md`
- 합성 PDF 안내: `output/pdf/rentguard-fixtures/README.md`

---

이 인수인계서는 코드보다 우선하는 명세가 아니다. 동작이 문서와 다르면 테스트와 현재 코드를 확인하고, 변경 후에는 이 문서도 함께 갱신한다.
