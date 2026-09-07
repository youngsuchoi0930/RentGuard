# RentGuard AI

전세계약 서류를 교차검증해 위험 신호와 계약 전 행동을 설명하는 서비스입니다.

현재 MVP는 주소/계약 조건과 등기부등본·건축물대장·임대차계약서를 입력받아 다음을 보여줍니다.

- 문서별 구조화 추출 결과
- 소유자/계약자, 보증금, 근저당, 위반건축물 교차검증
- 규칙 기반 위험 점수와 근거
- 계약 전에 해야 할 행동 추천

LLM은 최종 설명 계층에만 연결하도록 설계하며, 위험 판단은 재현 가능한 Rule/ML 계층에서 수행합니다.

## 실행

### Web

```bash
pnpm install
pnpm dev:web
```

http://localhost:3000 에서 확인할 수 있습니다. API가 실행 중이지 않으면 프런트엔드의 동일한 규칙 엔진으로 데모가 동작합니다.

### API

```bash
cd apps/api
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

API 문서는 http://localhost:8000/docs 에서 확인할 수 있습니다.

## 구조

```text
apps/web        Next.js 사용자 인터페이스
apps/api        FastAPI 분석 API와 위험도 엔진
docs            제품 및 아키텍처 문서
```

## 현재 데모의 경계

업로드 파일은 실제 OCR 대신 문서 종류별 샘플 추출기를 통과합니다. `apps/api/app`의 어댑터 경계를 CLOVA OCR/PaddleOCR, 국토교통부 실거래가, 건축HUB 클라이언트로 교체하면 같은 응답 스키마를 유지한 채 실제 데이터 파이프라인으로 확장할 수 있습니다.
