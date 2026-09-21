# 실제 문서 비공개 홀드아웃 검증

실제 등기부등본·건축물대장·임대차계약서는 합성 문서와 분리해
`local-fixtures`에서만 평가합니다. 이 디렉터리 전체는 `.gitignore`에 포함되어
PDF, 정답, 추출 결과가 Git에 올라가지 않습니다.

## 폴더 구조

```text
local-fixtures/
  case-001/
    registry.pdf
    building-ledger.pdf
    lease-contract.pdf
    expected.json
  case-002/
    ...
```

계약 전 사전점검 사례라면 `lease-contract.pdf`와 `expected.lease_contract`를
생략할 수 있습니다. `expected.json`에는 사람이 원문을 확인한 값만 기록합니다.
라벨을 작성하지 않은 필드는 평가에서 제외되며, 비어 있어야 하는 배열은 반드시
빈 배열(`[]`)로 기록해야 오탐을 계산할 수 있습니다.

```json
{
  "case_id": "CASE-002",
  "source_type": "real_anonymized",
  "input": {
    "address": "입력에 사용할 주소",
    "deposit": 30000000,
    "monthly_rent": 1300000
  },
  "expected": {
    "registry": {
      "owners": ["익명소유자"],
      "road_address": "문서의 도로명주소",
      "mortgages": []
    },
    "building_ledger": {
      "road_address": "문서의 도로명주소",
      "building_name": "건물명",
      "main_use": "공동주택",
      "is_illegal_building": false
    }
  }
}
```

## 실행

저장소 루트의 PowerShell에서 실행합니다.

```powershell
apps\api\.venv\Scripts\python scripts\evaluate_private_holdout.py
apps\api\.venv\Scripts\python scripts\evaluate_private_holdout.py --case case-001 --strict
```

결과는 기본적으로 Git에서 제외된
`local-fixtures/holdout-evaluation.json`에 저장됩니다.

- `field_accuracy`: 라벨을 작성한 필드 중 맞은 필드 비율
- `exact_field_accuracy`: 띄어쓰기까지 완전히 같은 필드 비율
- `false_positive_values`: 문서에 없거나 다른데 추출기가 있다고 판단한 값
- `false_negative_values`: 문서에 있는데 누락했거나 다르게 읽은 값
- `value_precision`: 추출한 값 중 맞은 값의 비율
- `value_recall`: 정답 값 중 찾아낸 값의 비율

실제 문서는 모델 학습에 넣지 않고 끝까지 홀드아웃으로 유지합니다. 추출 규칙이나
모델을 수정한 뒤 동일 사례를 다시 실행해 정확도가 개선되고 기존 사례가 퇴행하지
않았는지 확인합니다.
