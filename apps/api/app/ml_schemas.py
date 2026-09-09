from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .schemas import AnalysisResponse


MLLabel = Literal["unlabeled", "normal", "anomalous", "confirmed_risk"]
MLLabelSource = Literal["none", "reviewer", "confirmed_outcome", "synthetic"]


class MLDatasetRowRequest(BaseModel):
    analysis: AnalysisResponse
    source_kind: Literal["real_anonymized", "synthetic", "public_transaction"] = (
        "real_anonymized"
    )
    label: MLLabel = "unlabeled"
    label_source: MLLabelSource = "none"
    case_group_id: str | None = Field(
        default=None,
        min_length=8,
        max_length=80,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="주소나 이름 대신 운영자가 발급한 비식별 사례 묶음 ID",
    )
    reference_year: int | None = Field(default=None, ge=2000, le=2100)

    @model_validator(mode="after")
    def validate_label_provenance(self) -> "MLDatasetRowRequest":
        if self.label == "unlabeled" and self.label_source != "none":
            raise ValueError("미라벨 데이터의 label_source는 none이어야 합니다.")
        if self.label != "unlabeled" and self.label_source == "none":
            raise ValueError("라벨을 지정할 때는 근거가 되는 label_source가 필요합니다.")
        if self.label_source == "synthetic" and self.source_kind != "synthetic":
            raise ValueError("synthetic 라벨 근거는 합성 데이터에만 사용할 수 있습니다.")
        return self


class MLFeatureVector(BaseModel):
    analysis_mode: Literal["precheck", "contract_review"]
    housing_category: Literal[
        "apartment",
        "rowhouse_multifamily",
        "officetel",
        "detached_multihousehold",
        "other",
        "unknown",
    ]
    deposit_million_won: float = Field(ge=0)
    monthly_rent_million_won: float = Field(ge=0)
    mortgage_million_won: float = Field(ge=0)
    estimated_value_million_won: float | None = Field(default=None, gt=0)
    deposit_to_value_ratio: float | None = Field(default=None, ge=0)
    mortgage_to_value_ratio: float | None = Field(default=None, ge=0)
    total_burden_to_value_ratio: float | None = Field(default=None, ge=0)
    annual_rent_to_value_ratio: float | None = Field(default=None, ge=0)
    estimated_value_range_width_ratio: float | None = Field(default=None, ge=0)
    building_age_years: int | None = Field(default=None, ge=0)
    illegal_building_status: Literal["yes", "no", "unknown"]
    recent_transaction_count: int | None = Field(default=None, ge=0)
    local_price_volatility: float | None = Field(default=None, ge=0)
    market_data_status: Literal["not_connected", "available", "unavailable"]
    document_count: int = Field(ge=2, le=3)
    document_confidence_mean: float = Field(ge=0, le=1)
    document_confidence_min: float = Field(ge=0, le=1)
    corrected_field_count: int = Field(ge=0)
    unresolved_review_count: int = Field(ge=0)
    missing_feature_count: int = Field(ge=0)


class MLDatasetQuality(BaseModel):
    eligible_for_training: bool
    exclusion_reasons: list[
        Literal[
            "estimated_value_missing",
            "market_sample_too_small",
            "low_document_confidence",
            "too_many_missing_features",
        ]
    ] = Field(default_factory=list)


class MLDatasetRow(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    sample_id: str
    case_group_id: str | None = None
    created_at: datetime
    reference_year: int = Field(ge=2000, le=2100)
    source_kind: Literal["real_anonymized", "synthetic", "public_transaction"]
    label: MLLabel
    label_source: MLLabelSource
    features: MLFeatureVector
    quality: MLDatasetQuality


class PublicRentFeatureVector(BaseModel):
    district_code: str = Field(pattern=r"^11\d{3}$")
    district_name: str
    legal_dong_name: str
    housing_category: Literal["rowhouse_multifamily"] = "rowhouse_multifamily"
    contract_year: int = Field(ge=2000, le=2100)
    contract_month: int = Field(ge=1, le=12)
    exclusive_area_m2: float = Field(gt=0)
    floor: int | None = None
    building_age_years: int | None = Field(default=None, ge=0)
    deposit_million_won: float = Field(ge=0)
    monthly_rent_million_won: float = Field(ge=0)
    deposit_per_m2_million_won: float = Field(ge=0)
    monthly_rent_per_m2_million_won: float = Field(ge=0)
    contract_type: Literal["new", "renewal", "unknown"]
    renewal_right_used: Literal["yes", "no", "unknown"]
    previous_deposit_million_won: float | None = Field(default=None, ge=0)
    previous_monthly_rent_million_won: float | None = Field(default=None, ge=0)
    deposit_change_ratio: float | None = None
    monthly_rent_change_ratio: float | None = None


class PublicRentTrainingRow(BaseModel):
    schema_version: Literal["market-rent-1.0"] = "market-rent-1.0"
    sample_id: str
    source_kind: Literal["public_transaction", "synthetic"]
    source_api: Literal["MOLIT_RH_RENT"] = "MOLIT_RH_RENT"
    label: MLLabel = "unlabeled"
    label_source: MLLabelSource = "none"
    synthetic_scenario: Literal[
        "deposit_spike",
        "rent_spike",
        "renewal_jump",
    ] | None = None
    features: PublicRentFeatureVector
