# RentGuard PDF fixtures

개인정보가 없는 합성 문서 테스트 세트입니다. 모든 문서에는 `테스트 전용 · 법적 효력 없음` 워터마크가 있습니다.

| 파일 | 용도 |
|---|---|
| `registry_risky_digital.pdf` | 텍스트 레이어가 있는 등기부 추출 테스트 |
| `registry_risky_scan_noisy.pdf` | 회전·노이즈가 있는 이미지 OCR 테스트 |
| `building_ledger_risky.pdf` | 건축물대장 필드 추출 테스트 |
| `lease_contract_risky.pdf` | 임대차계약서 필드 및 특약 추출 테스트 |
| `ground_truth.json` | 예상 추출값과 교차검증 결과 |

## 공식 형식 참고 출처

- 법무부 주택임대차표준계약서: https://www.moj.go.kr/moj/314/subview.do
- 국가법령정보센터 건축물대장 별지 서식: https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=253085
- 정부24 건축물대장 발급 안내: https://www.gov.kr/mw/AA020InfoCappView.do?CappBizCD=15000000098

실제 부동산 등기사항증명서 구조는 인터넷등기소에서 본인 테스트 대상 주소의 열람본을 발급받아 별도 비공개 fixture로 사용하는 것을 권장합니다. Git 저장소에 개인정보가 포함된 문서를 커밋하지 마세요.
