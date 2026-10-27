# 개발·재현 가이드

명령은 저장소 루트의 Windows PowerShell 기준입니다. 기본 실행은 [README](../README.md), 상세 운영 상태는 [HANDOFF](../HANDOFF.md)를 참고합니다.

## API

분석 흐름은 `PDF 업로드 → 추출값 확인 → 공공데이터 대조·분석`의 두 단계입니다.
오류를 목업 결과로 대체하지 않습니다. `analysis_mode`는 `precheck` 또는 `contract_review`입니다.
JSON 재분석 요청의 필드명은 `mode`이며 Swagger의 요청 스키마를 확인합니다.

| 엔드포인트 | 기능 |
|---|---|
| `POST /api/v1/documents/registry/extract` | 등기사항증명서 추출 |
| `POST /api/v1/documents/building-ledger/extract` | 건축물대장 추출 |
| `POST /api/v1/documents/lease-contract/extract` | 계약서 추출 |
| `GET /api/v1/addresses/search` | 도로명주소·지번·법정동 코드 |
| `POST /api/v1/document-bundles/extract` | 모드별 문서 일괄 추출 |
| `POST /api/v1/analyses` | 문서 업로드부터 위험 분석까지 실행 |
| `POST /api/v1/analyses/from-extractions` | 확인·수정된 추출값으로 분석 |
| `POST /api/v1/ml/dataset-rows/preview` | 저장 없이 비식별 학습 행 미리보기 |
| `GET /api/v1/analysis-history` | 비식별 기록 목록 |
| `GET /api/v1/analysis-history/{analysis_id}` | 기록 상세 |
| `DELETE /api/v1/analysis-history` | 전체 기록과 피드백 삭제 |
| `DELETE /api/v1/analysis-history/{analysis_id}` | 개별 삭제 |
| `GET`, `POST /api/v1/analysis-history/{analysis_id}/feedback` | 분석별 피드백 조회·저장 |
| `GET /api/v1/feedback` | 피드백 통계·내역 |
| `PATCH /api/v1/feedback/{feedback_id}/review` | 승인·대기·제외 검수 |
| `GET /api/v1/feedback/export?format=csv` | 승인 품질 기준 충족 시 CSV/JSON 내보내기 |

`save_history=false`가 기본이며 동의 시에만 `retention_days=7/30/90`으로 저장합니다.
PDF·OCR 원문·이름·문서 증거는 기록에서 제거하고 상세주소는 시·구 수준으로 축약합니다.
피드백은 판정과 숫자 수정값만 저장하고 자유 입력 원문은 받지 않습니다.
학습용 내보내기는 승인 피드백 20건과 서로 다른 분석 5건 이상이 필요합니다.

## 검증

```powershell
apps/api/.venv/Scripts/python -m pip install -r apps/api/requirements-ci.txt
Push-Location apps/api
.venv/Scripts/python -m pytest -q
Pop-Location
pnpm lint:web
pnpm build:web
pnpm --dir apps/web exec playwright install chromium
pnpm test:e2e
pnpm audit:web
apps/api/.venv/Scripts/python -m pip_audit -r apps/api/requirements-ci.txt
apps/api/.venv/Scripts/python -m pip_audit -r apps/api/requirements.txt
docker compose config -q
```

Playwright는 API 응답을 모킹하는 Chromium 브라우저 흐름 테스트입니다.
실제 OCR·공공 API·LLM 통합 검증과 구분하며, 개발 서버를 3100 포트에서 자동 실행합니다.
상세 점검 시점과 범위는 [릴리스 점검표](release-readiness-checklist.md)에 있습니다.

### 합성 문서·스캔 OCR

```powershell
apps/api/.venv/Scripts/python scripts/generate_synthetic_document_corpus.py
apps/api/.venv/Scripts/python scripts/evaluate_synthetic_document_corpus.py --strict
apps/api/.venv/Scripts/python scripts/evaluate_registry.py --pdf output/pdf/rentguard-fixtures/registry_risky_digital.pdf --no-ocr --json
Push-Location apps/api
$env:RUN_OCR_TESTS = "1"
.venv/Scripts/python -m pytest -q -m ocr
Remove-Item Env:RUN_OCR_TESTS
Pop-Location
```

실제 문서의 엄격 회귀는 [비공개 홀드아웃 가이드](private-holdout-guide.md)를 따릅니다.
`--update-baseline`은 승인한 정답 기준선을 교체하는 작업이므로 기본 평가와 구분합니다.

## 데이터 수집·학습·기준선 비교

국토부 전월세 API 활용신청과 `DATA_GO_KR_SERVICE_KEY`가 필요합니다. 출력 거래에는 지번·건물명을 저장하지 않습니다.
학습 행 정의는 [ml-dataset-v1.md](ml-dataset-v1.md), 평가 해석은 [모델 카드](model-card.md)에 있습니다.

```powershell
apps/api/.venv/Scripts/python -m pip install -r apps/api/requirements-ml.txt
apps/api/.venv/Scripts/python scripts/collect_rent_market.py --months 24
apps/api/.venv/Scripts/python scripts/inspect_rent_dataset.py data/ml/seoul-rh-rent-market-v1.jsonl
apps/api/.venv/Scripts/python scripts/generate_synthetic_rent_data.py --count 20000
apps/api/.venv/Scripts/python scripts/train_market_anomaly.py
apps/api/.venv/Scripts/python scripts/train_deposit_quantile.py
apps/api/.venv/Scripts/python scripts/evaluate_deposit_baseline.py
```

기존 학습 출력은 `--force` 없이 덮어쓰지 않습니다. 공개 기준선 평가는 원자료 SHA-256·모델 manifest·홀드아웃 건수·v2 MAE가 기존 평가와 일치해야 집계를 생성합니다.
다른 자료·모델의 평가에는 별도 `--input`, `--report`, `--model`, `--output`을 사용합니다.
모델은 신뢰하는 로컬 학습 산출물만 로드하고 업로드 파일을 모델로 사용하지 않습니다.

## README 화면 재현

한 터미널에서 웹을 실행합니다.

```powershell
pnpm --dir apps/web dev --hostname 127.0.0.1 --port 3101
```

다른 터미널에서 캡처합니다. Node.js 22.18 이상 또는 24에서 TypeScript 타입 제거 기능을 사용합니다.

```powershell
Push-Location apps/web
node --experimental-strip-types scripts/capture-readme-demo.mts
Pop-Location
```

`user1` 프로필의 빈 첫 화면을 원본 배경과 구성을 유지하여 `docs/screenshots/home.png`로 캡처합니다. 합성 E2E fixture를 업로드하고 API 응답을 모킹하여 같은 폴더의 입력·확인·결과 PNG도 재생성합니다.
공공 API·Gemini·개인 원본 문서에는 접근하지 않습니다. 현재 캡처는 데스크톱 화면이며 실제 서비스 성능이나 모델 평가의 증거로 사용하지 않습니다.

`result-masked.png`는 사용자가 제공한 실제 결과의 표시값을 기준으로 만든 아파트 사례의 전체 화면입니다.
공개용 입력은 `apps/web/scripts/masked-apartment-demo.mts`에 있으며, 주소·이름·원문 식별정보·분석 ID는 처음부터 가상 값으로 작성합니다.
사전 마스킹한 응답으로 실제 UI를 재현하므로 원본 스크린샷의 개인정보가 Git에 들어가지 않습니다. 아파트 ML 범위 밖·건축HUB 오류·피드백 영역을 한 장에서 확인할 수 있습니다.
