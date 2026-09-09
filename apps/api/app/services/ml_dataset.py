from datetime import datetime, timezone
from uuid import uuid4

from ..ml_schemas import (
    MLDatasetQuality,
    MLDatasetRow,
    MLDatasetRowRequest,
    MLFeatureVector,
)


def _ratio(numerator: int, denominator: int | None) -> float | None:
    if denominator is None or denominator <= 0:
        return None
    return round(numerator / denominator, 6)


def _million_won(value: int) -> float:
    return round(value / 1_000_000, 6)


def _housing_category(building_use: str | None) -> str:
    if not building_use:
        return "unknown"
    normalized = building_use.replace(" ", "")
    if "오피스텔" in normalized:
        return "officetel"
    if "아파트" in normalized:
        return "apartment"
    if "다세대" in normalized or "연립" in normalized:
        return "rowhouse_multifamily"
    if "단독" in normalized or "다가구" in normalized:
        return "detached_multihousehold"
    return "other"


def _document_confidences(request: MLDatasetRowRequest) -> list[float]:
    documents = request.analysis.documents
    confidences = [documents.registry.confidence, documents.building_ledger.confidence]
    if documents.lease_contract is not None:
        confidences.append(documents.lease_contract.confidence)
    return confidences


def _unresolved_review_count(request: MLDatasetRowRequest) -> int:
    documents = request.analysis.documents
    count = len(documents.registry.needs_review) + len(documents.building_ledger.needs_review)
    if documents.lease_contract is not None:
        count += len(documents.lease_contract.needs_review)
    count += sum(
        item.status in {"mismatch", "needs_review"}
        for item in documents.cross_checks
    )
    return count


def build_ml_dataset_row(request: MLDatasetRowRequest) -> MLDatasetRow:
    """Create a non-PII feature row without copying rule scores or OCR text."""
    analysis = request.analysis
    facts = analysis.facts
    created_at = datetime.now(timezone.utc)
    reference_year = request.reference_year or created_at.year
    estimated_value = facts.estimated_value
    confidences = _document_confidences(request)

    range_width_ratio = None
    if (
        estimated_value
        and facts.estimated_value_low is not None
        and facts.estimated_value_high is not None
    ):
        range_width_ratio = round(
            (facts.estimated_value_high - facts.estimated_value_low) / estimated_value,
            6,
        )

    building_age = None
    if facts.approval_year is not None and facts.approval_year <= reference_year:
        building_age = reference_year - facts.approval_year

    housing_category = _housing_category(facts.building_use)
    illegal_status = (
        "unknown"
        if facts.is_illegal_building is None
        else "yes" if facts.is_illegal_building else "no"
    )
    missing_feature_count = sum(
        value is None or value == "unknown"
        for value in (
            estimated_value,
            housing_category,
            building_age,
            illegal_status,
            facts.recent_transactions,
            facts.local_price_volatility,
        )
    )

    features = MLFeatureVector(
        analysis_mode=analysis.mode,
        housing_category=housing_category,
        deposit_million_won=_million_won(facts.deposit),
        monthly_rent_million_won=_million_won(facts.monthly_rent),
        mortgage_million_won=_million_won(facts.mortgage_amount),
        estimated_value_million_won=(
            _million_won(estimated_value) if estimated_value is not None else None
        ),
        deposit_to_value_ratio=_ratio(facts.deposit, estimated_value),
        mortgage_to_value_ratio=_ratio(facts.mortgage_amount, estimated_value),
        total_burden_to_value_ratio=_ratio(
            facts.deposit + facts.mortgage_amount,
            estimated_value,
        ),
        annual_rent_to_value_ratio=_ratio(
            facts.monthly_rent * 12,
            estimated_value,
        ),
        estimated_value_range_width_ratio=range_width_ratio,
        building_age_years=building_age,
        illegal_building_status=illegal_status,
        recent_transaction_count=facts.recent_transactions,
        local_price_volatility=facts.local_price_volatility,
        market_data_status=analysis.market_data.status,
        document_count=len(confidences),
        document_confidence_mean=round(sum(confidences) / len(confidences), 6),
        document_confidence_min=min(confidences),
        corrected_field_count=len(analysis.corrections),
        unresolved_review_count=_unresolved_review_count(request),
        missing_feature_count=missing_feature_count,
    )

    exclusion_reasons = []
    if estimated_value is None:
        exclusion_reasons.append("estimated_value_missing")
    if facts.recent_transactions is None or facts.recent_transactions < 5:
        exclusion_reasons.append("market_sample_too_small")
    if min(confidences) < 0.7:
        exclusion_reasons.append("low_document_confidence")
    if missing_feature_count > 2:
        exclusion_reasons.append("too_many_missing_features")

    return MLDatasetRow(
        sample_id=str(uuid4()),
        case_group_id=request.case_group_id,
        created_at=created_at,
        reference_year=reference_year,
        source_kind=request.source_kind,
        label=request.label,
        label_source=request.label_source,
        features=features,
        quality=MLDatasetQuality(
            eligible_for_training=not exclusion_reasons,
            exclusion_reasons=exclusion_reasons,
        ),
    )
