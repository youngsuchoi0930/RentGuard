from __future__ import annotations

import re

from ..building_schemas import BuildingLedgerExtraction
from ..cross_check_schemas import CrossCheckItem, DocumentBundleExtraction
from ..lease_schemas import LeaseContractExtraction
from ..registry_schemas import RegistryExtraction


def _normalized(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"[^0-9A-Za-z가-힣]", "", value).lower()


def _address_key(value: str | None) -> str | None:
    if not value:
        return None
    # Registry OCR can retain a document-type prefix such as "[집합건물]".
    # It is not part of the property address and must not cause a mismatch.
    without_heading = re.sub(r"^\s*\[[^\]]+\]\s*", "", value)
    match = re.search(r"(.+?(?:대로|로|길)\s*\d+(?:-\d+)?)", without_heading)
    return _normalized(match.group(1) if match else without_heading)


def _matches(left: str | None, right: str | None) -> bool | None:
    left_value = _normalized(left)
    right_value = _normalized(right)
    if not left_value or not right_value:
        return None
    return left_value == right_value


def _address_matches(*values: str | None) -> bool | None:
    keys = [_address_key(value) for value in values if value]
    if len(keys) < 2:
        return None
    return len(set(keys)) == 1


def _item(
    *,
    id: str,
    label: str,
    result: bool | None,
    success: str,
    failure: str,
    review: str,
    values: dict[str, str | int | bool | None],
) -> CrossCheckItem:
    if result is True:
        status, detail = "verified", success
    elif result is False:
        status, detail = "mismatch", failure
    else:
        status, detail = "needs_review", review
    return CrossCheckItem(id=id, status=status, label=label, detail=detail, values=values)


def cross_check_documents(
    registry: RegistryExtraction,
    building_ledger: BuildingLedgerExtraction,
    lease_contract: LeaseContractExtraction | None,
    *,
    input_address: str,
    input_deposit: int,
    input_monthly_rent: int,
) -> DocumentBundleExtraction:
    owner = registry.ownership[0].owner_name if registry.ownership else None
    registry_address = registry.property.road_address or registry.property.lot_address
    ledger_address = building_ledger.property.road_address or building_ledger.property.lot_address

    if lease_contract is None:
        checks = [
            _item(
                id="registry-owner",
                label="등기 소유자 확인",
                result=True if owner else None,
                success="등기부에서 현재 소유자를 확인했습니다.",
                failure="등기 소유자를 확인하지 못했습니다.",
                review="등기 소유자를 추출하지 못해 원문 확인이 필요합니다.",
                values={"registry_owner": owner},
            ),
            _item(
                id="property-address",
                label="입력 주소와 두 문서",
                result=(
                    _address_matches(input_address, registry_address, ledger_address)
                    if registry_address and ledger_address
                    else None
                ),
                success="입력 주소와 두 문서의 도로명주소가 일치합니다.",
                failure="입력 주소와 두 문서 중 하나 이상의 주소가 다릅니다.",
                review="주소를 충분히 추출하지 못해 원문 확인이 필요합니다.",
                values={
                    "input": input_address,
                    "registry": registry_address,
                    "building_ledger": ledger_address,
                },
            ),
            _item(
                id="illegal-building",
                label="위반건축물 여부",
                result=(not building_ledger.property.is_illegal_building)
                if building_ledger.property.is_illegal_building is not None else None,
                success="건축물대장에서 위반건축물 표기가 확인되지 않았습니다.",
                failure="건축물대장에 위반건축물 표기가 있습니다.",
                review="위반건축물 여부를 추출하지 못했습니다.",
                values={"is_illegal_building": building_ledger.property.is_illegal_building},
            ),
        ]
        return DocumentBundleExtraction(
            registry=registry,
            building_ledger=building_ledger,
            lease_contract=None,
            cross_checks=checks,
        )

    landlord = next((party.name for party in lease_contract.parties if party.role == "landlord"), None)
    contract_address = lease_contract.property.address
    contract_deposit = lease_contract.deposit.value
    contract_monthly_rent = lease_contract.monthly_rent.value
    checks = [
        _item(
            id="owner-landlord",
            label="등기 소유자와 계약서 임대인",
            result=_matches(owner, landlord),
            success="등기 소유자와 계약서 임대인이 일치합니다.",
            failure="등기 소유자와 계약서 임대인이 다릅니다.",
            review="소유자 또는 임대인을 추출하지 못해 확인이 필요합니다.",
            values={"registry_owner": owner, "contract_landlord": landlord},
        ),
        _item(
            id="property-address",
            label="세 문서와 입력 주소",
            result=_address_matches(input_address, registry_address, ledger_address, contract_address),
            success="입력 주소와 세 문서의 도로명주소가 일치합니다.",
            failure="입력 주소와 문서 중 하나 이상의 주소가 다릅니다.",
            review="주소를 충분히 추출하지 못해 원문 확인이 필요합니다.",
            values={
                "input": input_address,
                "registry": registry_address,
                "building_ledger": ledger_address,
                "lease_contract": contract_address,
            },
        ),
        _item(
            id="deposit",
            label="입력 보증금과 계약서",
            result=input_deposit == contract_deposit if contract_deposit is not None else None,
            success="입력 보증금과 계약서 보증금이 일치합니다.",
            failure="입력 보증금과 계약서 보증금이 다릅니다.",
            review="계약서 보증금을 추출하지 못했습니다.",
            values={"input": input_deposit, "lease_contract": contract_deposit},
        ),
        _item(
            id="monthly-rent",
            label="입력 월세와 계약서",
            result=input_monthly_rent == contract_monthly_rent if contract_monthly_rent is not None else None,
            success="입력 월세와 계약서 월세가 일치합니다.",
            failure="입력 월세와 계약서 월세가 다릅니다.",
            review="계약서 월세를 추출하지 못했습니다.",
            values={"input": input_monthly_rent, "lease_contract": contract_monthly_rent},
        ),
        _item(
            id="illegal-building",
            label="위반건축물 여부",
            result=(not building_ledger.property.is_illegal_building)
            if building_ledger.property.is_illegal_building is not None else None,
            success="건축물대장에서 위반건축물 표기가 확인되지 않았습니다.",
            failure="건축물대장에 위반건축물 표기가 있습니다.",
            review="위반건축물 여부를 추출하지 못했습니다.",
            values={"is_illegal_building": building_ledger.property.is_illegal_building},
        ),
    ]
    return DocumentBundleExtraction(
        registry=registry,
        building_ledger=building_ledger,
        lease_contract=lease_contract,
        cross_checks=checks,
    )
