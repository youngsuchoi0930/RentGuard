# RentGuard synthetic document corpus

개인정보 없이 문서 추출기와 교차검증 로직을 반복 시험하기 위한 30건 합성 코퍼스다.

- `rentguard-synthetic-corpus-30.pdf`: 케이스당 등기부·건축물대장·임대차계약서 3페이지, 총 90페이지
- `manifest.json`: 사람이 정의한 입력값과 필드별 정답
- `evaluation.json`: 현재 파서가 정답을 얼마나 재현했는지 기록한 자동평가 결과

모든 레코드는 `source_kind=synthetic`으로 표시한다. 실제 사람·주소·건물·계약과 관계가 없으며 실제 성능 평가나 법적 판단에 사용하지 않는다.

## 시나리오 구성

| 시나리오 | 건수 |
|---|---:|
| 권리사항 없음 | 5 |
| 낮은 근저당 | 4 |
| 높은 근저당 | 4 |
| 근저당 2건 | 2 |
| 소유자·임대인 불일치 | 2 |
| 주소 불일치 | 2 |
| 보증금 불일치 | 2 |
| 월세 불일치 | 1 |
| 위반건축물 | 2 |
| 압류·가압류·신탁·경매 | 4 |
| 말소된 근저당 | 1 |
| 복합 고위험 | 1 |

현재 기준 자동평가는 30건 전체, 480개 필드를 모두 통과한다.

생성 및 평가:

```powershell
apps\api\.venv\Scripts\python -m pip install -r scripts\requirements-pdf.txt
apps\api\.venv\Scripts\python scripts\generate_synthetic_document_corpus.py
apps\api\.venv\Scripts\python scripts\evaluate_synthetic_document_corpus.py --strict
```
