from typing import Literal

from pydantic import BaseModel

from .building_schemas import BuildingLedgerExtraction
from .lease_schemas import LeaseContractExtraction
from .registry_schemas import RegistryExtraction


class CrossCheckItem(BaseModel):
    id: str
    status: Literal["verified", "mismatch", "needs_review"]
    label: str
    detail: str
    values: dict[str, str | int | bool | None]


class DocumentBundleExtraction(BaseModel):
    registry: RegistryExtraction
    building_ledger: BuildingLedgerExtraction
    lease_contract: LeaseContractExtraction
    cross_checks: list[CrossCheckItem]

