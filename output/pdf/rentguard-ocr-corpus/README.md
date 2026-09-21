# RentGuard OCR regression corpus

텍스트 레이어가 없는 이미지 전용 합성 문서 10건이다. 각 사례는 등기부·건축물대장·임대차계약서 3페이지로 구성되며 회전, 흐림, 명암, 노이즈, 저해상도, JPEG 압축 변형을 포함한다.

- `rentguard-ocr-corpus-10.pdf`: 10건, 총 30페이지
- `manifest.json`: 원본 합성 사례, 변형 조건, 필드별 정답
- `evaluation.json`: PaddleOCR 추출 결과와 필드별 비교

모든 데이터는 `source_kind=synthetic_ocr`이며 실제 문서 성능을 주장하는 평가 자료로 사용하지 않는다.

주소 필드는 원문 완전일치와 서비스가 사용하는 공백·문장부호 제외 일치를 둘 다 기록한다. 어느 값이 다른지 숨기지 않도록 `exact_accuracy`와 의미상 `accuracy`를 분리한다.

```powershell
apps\api\.venv\Scripts\python scripts\generate_ocr_document_corpus.py
apps\api\.venv\Scripts\python scripts\evaluate_ocr_document_corpus.py --min-accuracy 0.90
```
