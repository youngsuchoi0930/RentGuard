# RentGuard AI

전세계약 서류를 교차검증해 위험 신호와 계약 전 행동을 설명하는 서비스입니다.

현재 MVP는 주소/계약 조건과 등기부등본·건축물대장·임대차계약서를 입력받아 다음을 보여줍니다.

- 문서별 구조화 추출 결과
- 소유자/계약자, 보증금, 근저당, 위반건축물 교차검증
- 규칙 기반 위험 점수와 근거
- 개인정보를 제외한 구조화 결과의 Gemini 쉬운 설명
- 계약 전에 해야 할 행동 추천

LLM은 최종 설명 계층에만 연결하도록 설계하며, 위험 판단은 재현 가능한 Rule/ML 계층에서 수행합니다.

Gemini 설명 기능은 저장소 루트의 `.env`에 `GEMINI_API_KEY`를 설정하면 활성화됩니다. 기존 로컬 설정과의 호환을 위해 `gemini_key`도 인식합니다. 모델 기본값은 무료 등급을 지원하는 `gemini-3.5-flash-lite`이며 `GEMINI_MODEL`로 변경할 수 있습니다. Gemini에는 PDF 원문, 주소, 이름, 금액, 증거 원문을 보내지 않고 위험 신호 범주와 검증 상태만 전송합니다. 키가 없거나 호출·검증에 실패하면 규칙 기반 결과만 반환합니다.

## 실행

아래 명령은 Windows `cmd` 기준입니다.

### Web

```bat
corepack enable
corepack prepare pnpm@latest --activate
pnpm install
pnpm dev:web
```

http://localhost:3000 에서 확인할 수 있습니다. 프런트엔드는 실제 `POST /api/v1/analyses` 응답만 표시하며, OCR이 끝날 때까지 진행 화면을 유지합니다. API 오류는 목업 결과로 대체하지 않고 입력 화면에 표시합니다.

### API

```bat
cd apps/api
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

Windows 로컬 OCR 환경은 PaddlePaddle 휠과 맞는 Python 3.12를 사용합니다. Python 3.14로 가상환경을 만들면 OCR 의존성을 설치할 수 없습니다.

API 문서는 http://localhost:8000/docs 에서 확인할 수 있습니다.

## 등기부 PDF 추출·비교 테스트

등기부 추출기는 먼저 PDF 텍스트 레이어를 사용하고, 텍스트가 없는 스캔 PDF만 PaddleOCR로 처리합니다. 표의 좌표나 고정된 셀 순서에 의존하지 않고 `소유자`, `근저당권설정`, `채권최고액` 같은 의미 표식을 중심으로 필드를 묶습니다. 반복될 수 있는 소유권과 권리사항은 배열이며, 각 항목에는 페이지·원문·추출 방식·신뢰도를 남깁니다.

테스트용 합성 문서와 정답은 `output/pdf/rentguard-fixtures`에 있습니다.

```bat
REM 빠른 테스트: 텍스트 PDF와 API (OCR 모델 실행 제외)
cd apps\api
.venv\Scripts\python -m pytest -q -m "not ocr"

REM 스캔 PDF OCR 비교: 최초 실행 시 한국어 모델 다운로드
set RUN_OCR_TESTS=1
.venv\Scripts\python -m pytest -q -m ocr
```

정답과 필드별 비교 결과를 JSON으로 직접 보려면 저장소 루트에서 실행합니다.

```bat
apps\api\.venv\Scripts\python scripts\evaluate_registry.py --pdf output\pdf\rentguard-fixtures\registry_risky_digital.pdf --no-ocr --json
apps\api\.venv\Scripts\python scripts\evaluate_registry.py --pdf output\pdf\rentguard-fixtures\registry_risky_scan_noisy.pdf --json
```

실행 중인 API에 PDF를 업로드하는 엔드포인트는 `POST /api/v1/documents/registry/extract`입니다. Swagger 문서의 **Try it out**에서 바로 시험할 수 있습니다.

추가된 백엔드 문서 API는 다음과 같습니다.

| 엔드포인트 | 기능 |
|---|---|
| `POST /api/v1/documents/registry/extract` | 등기사항증명서 추출 |
| `POST /api/v1/documents/building-ledger/extract` | 건축물대장 추출 |
| `POST /api/v1/documents/lease-contract/extract` | 임대차계약서 추출 |
| `POST /api/v1/document-bundles/extract` | 세 문서 추출 및 주소·소유자·금액 교차검증 |
| `POST /api/v1/analyses` | 세 문서를 실제 추출·교차검증한 뒤 문서 기반 위험 신호 생성 |

`POST /api/v1/analyses`는 세 PDF를 모두 필수로 받습니다. 공공 실거래가가 연결되기 전에는 `estimated_value`, 최근 거래 수, 가격 변동성을 `null`로 반환하고 `market_data.status`를 `not_connected`로 표시합니다. 이 상태에서는 시세 대비 보증금·근저당 비율을 계산하지 않습니다.

실제 샘플 확보와 익명화 방법은 `docs/sample-data-guide.md`를 참고합니다.

## 구조

```text
apps/web        Next.js 사용자 인터페이스
apps/api        FastAPI 분석 API와 위험도 엔진
docs            제품 및 아키텍처 문서
scripts         합성 PDF 생성 및 추출 정확도 비교 도구
output/pdf      테스트용 합성 PDF와 정답 데이터
```

## 현재 데모의 경계

세 문서의 텍스트 추출과 OCR, 주요 필드 추출, 교차검증과 문서 기반 위험 신호까지 실제로 동작합니다. CASE-001 익명화 실문서 레이아웃으로도 검증했고, 프런트엔드도 장시간 OCR 응답을 기다린 뒤 실제 결과 또는 오류를 표시합니다. 국토교통부/건축HUB 시세 연동은 아직 남아 있습니다. 자동 추출 실패나 일부증명서는 `needs_review`로 보내며, 실제 계약 판단에는 원문 확인이 필요합니다.
