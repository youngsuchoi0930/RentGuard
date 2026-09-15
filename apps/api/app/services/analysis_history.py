from __future__ import annotations

import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, create_engine, func, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from ..config import Settings, get_settings
from ..schemas import (
    AIExplanation,
    AnalysisFeedbackCreate,
    AnalysisFeedbackItem,
    AnalysisFeedbackList,
    AnalysisHistoryDetail,
    AnalysisHistoryList,
    AnalysisHistorySummary,
    AnalysisResponse,
)


class Base(DeclarativeBase):
    pass


class AnalysisRecord(Base):
    __tablename__ = "analysis_history"

    analysis_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    masked_address: Mapped[str] = mapped_column(String(120))
    mode: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24))
    score: Mapped[int] = mapped_column(Integer)
    grade: Mapped[str] = mapped_column(String(12))
    headline: Mapped[str] = mapped_column(String(240))
    deposit: Mapped[int] = mapped_column(Integer)
    monthly_rent: Mapped[int] = mapped_column(Integer)
    estimated_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mortgage_amount: Mapped[int] = mapped_column(Integer)
    payload_json: Mapped[str] = mapped_column(Text)


class AnalysisFeedbackRecord(Base):
    __tablename__ = "analysis_feedback"
    __table_args__ = (
        UniqueConstraint("analysis_id", "target", name="uq_feedback_analysis_target"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[str] = mapped_column(String(36), index=True)
    target: Mapped[str] = mapped_column(String(32))
    verdict: Mapped[str] = mapped_column(String(16))
    original_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    corrected_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


def mask_address(address: str) -> str:
    normalized = re.sub(r"\s+", " ", address).strip()
    parts = normalized.split()
    if len(parts) >= 2:
        return f"{parts[0]} {parts[1]} · 상세주소 비공개"
    return "주소 비공개"


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _redact(text: str | None, private_values: tuple[str, ...]) -> str | None:
    if text is None:
        return None
    redacted = text
    for value in private_values:
        if value:
            redacted = redacted.replace(value, "[개인정보 비공개]")
    return redacted


class AnalysisHistoryStore:
    def __init__(self, database_path: Path):
        self.database_path = database_path.resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            URL.create("sqlite+pysqlite", database=str(self.database_path)),
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
        )
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)

    def health(self) -> dict[str, str]:
        self.initialize()
        with self.engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        return {"status": "ready", "engine": "sqlite"}

    def save(self, address: str, analysis: AnalysisResponse) -> AnalysisHistoryDetail:
        self.initialize()
        created_at = datetime.now(timezone.utc)
        masked_address = mask_address(address)
        private_values = tuple(
            value
            for value in (
                address.strip(),
                analysis.facts.owner or "",
                analysis.facts.contract_owner or "",
            )
            if value
        )
        facts = analysis.facts.model_copy(
            update={"owner": None, "contract_owner": None}
        )
        signals = [
            signal.model_copy(
                update={
                    "title": _redact(signal.title, private_values),
                    "description": _redact(signal.description, private_values),
                    "evidence": _redact(signal.evidence, private_values),
                    "sources": [],
                }
            )
            for signal in analysis.signals
        ]
        checks = [
            check.model_copy(
                update={
                    "label": _redact(check.label, private_values),
                    "detail": _redact(check.detail, private_values),
                    "sources": [],
                }
            )
            for check in analysis.checks
        ]
        ai_explanation = AIExplanation(
            **{
                **analysis.ai_explanation.model_dump(),
                "overview": _redact(analysis.ai_explanation.overview, private_values),
                "caution": _redact(analysis.ai_explanation.caution, private_values),
                "limitation": _redact(analysis.ai_explanation.limitation, private_values),
                "privacy_note": _redact(analysis.ai_explanation.privacy_note, private_values),
                "message": _redact(analysis.ai_explanation.message, private_values),
            }
        )
        detail = AnalysisHistoryDetail(
            analysis_id=analysis.analysis_id,
            created_at=created_at,
            masked_address=masked_address,
            mode=analysis.mode,
            status=analysis.status,
            score=analysis.score,
            grade=analysis.grade,
            headline=_redact(analysis.headline, private_values) or "분석 결과",
            deposit=analysis.facts.deposit,
            monthly_rent=analysis.facts.monthly_rent,
            estimated_value=analysis.facts.estimated_value,
            mortgage_amount=analysis.facts.mortgage_amount,
            summary=_redact(analysis.summary, private_values) or "분석 결과를 확인했습니다.",
            facts=facts,
            signals=signals,
            checks=checks,
            actions=[
                _redact(action, private_values) or "추가 확인이 필요합니다."
                for action in analysis.actions
            ],
            market_data=analysis.market_data.model_copy(
                update={"message": _redact(analysis.market_data.message, private_values)}
            ),
            deposit_market=analysis.deposit_market.model_copy(
                update={"message": _redact(analysis.deposit_market.message, private_values)}
            ),
            ai_explanation=ai_explanation,
        )
        record = AnalysisRecord(
            analysis_id=detail.analysis_id,
            created_at=detail.created_at,
            masked_address=detail.masked_address,
            mode=detail.mode,
            status=detail.status,
            score=detail.score,
            grade=detail.grade,
            headline=detail.headline,
            deposit=detail.deposit,
            monthly_rent=detail.monthly_rent,
            estimated_value=detail.estimated_value,
            mortgage_amount=detail.mortgage_amount,
            payload_json=detail.model_dump_json(),
        )
        with self.sessions.begin() as session:
            session.add(record)
        return detail

    @staticmethod
    def _summary(record: AnalysisRecord) -> AnalysisHistorySummary:
        return AnalysisHistorySummary(
            analysis_id=record.analysis_id,
            created_at=_utc(record.created_at),
            masked_address=record.masked_address,
            mode=record.mode,
            status=record.status,
            score=record.score,
            grade=record.grade,
            headline=record.headline,
            deposit=record.deposit,
            monthly_rent=record.monthly_rent,
            estimated_value=record.estimated_value,
            mortgage_amount=record.mortgage_amount,
        )

    def list(self, *, limit: int = 50, offset: int = 0) -> AnalysisHistoryList:
        self.initialize()
        with self.sessions() as session:
            records = session.scalars(
                select(AnalysisRecord)
                .order_by(AnalysisRecord.created_at.desc())
                .offset(offset)
                .limit(limit)
            ).all()
            total = session.scalar(select(func.count()).select_from(AnalysisRecord)) or 0
        return AnalysisHistoryList(
            items=[self._summary(record) for record in records],
            total=total,
        )

    def get(self, analysis_id: str) -> AnalysisHistoryDetail | None:
        self.initialize()
        with self.sessions() as session:
            record = session.get(AnalysisRecord, analysis_id)
            if record is None:
                return None
            return AnalysisHistoryDetail.model_validate_json(record.payload_json)

    @staticmethod
    def _feedback_item(record: AnalysisFeedbackRecord) -> AnalysisFeedbackItem:
        return AnalysisFeedbackItem(
            id=record.id,
            analysis_id=record.analysis_id,
            target=record.target,
            verdict=record.verdict,
            original_value=record.original_value,
            corrected_value=record.corrected_value,
            created_at=_utc(record.created_at),
            updated_at=_utc(record.updated_at),
        )

    def save_feedback(
        self,
        analysis_id: str,
        payload: AnalysisFeedbackCreate,
    ) -> AnalysisFeedbackItem | None:
        self.initialize()
        now = datetime.now(timezone.utc)
        with self.sessions.begin() as session:
            analysis_record = session.get(AnalysisRecord, analysis_id)
            if analysis_record is None:
                return None

            detail = AnalysisHistoryDetail.model_validate_json(
                analysis_record.payload_json
            )
            original_values = {
                "estimated_value": detail.facts.estimated_value,
                "mortgage_amount": detail.facts.mortgage_amount,
                "deposit": detail.facts.deposit,
                "monthly_rent": detail.facts.monthly_rent,
            }
            feedback = session.scalar(
                select(AnalysisFeedbackRecord).where(
                    AnalysisFeedbackRecord.analysis_id == analysis_id,
                    AnalysisFeedbackRecord.target == payload.target,
                )
            )
            if feedback is None:
                feedback = AnalysisFeedbackRecord(
                    analysis_id=analysis_id,
                    target=payload.target,
                    verdict=payload.verdict,
                    original_value=original_values.get(payload.target),
                    corrected_value=payload.corrected_value,
                    created_at=now,
                    updated_at=now,
                )
                session.add(feedback)
            else:
                feedback.verdict = payload.verdict
                feedback.corrected_value = payload.corrected_value
                feedback.updated_at = now
            session.flush()
            return self._feedback_item(feedback)

    def list_feedback(self, analysis_id: str) -> AnalysisFeedbackList | None:
        self.initialize()
        with self.sessions() as session:
            if session.get(AnalysisRecord, analysis_id) is None:
                return None
            records = session.scalars(
                select(AnalysisFeedbackRecord)
                .where(AnalysisFeedbackRecord.analysis_id == analysis_id)
                .order_by(AnalysisFeedbackRecord.updated_at.desc())
            ).all()
        return AnalysisFeedbackList(
            items=[self._feedback_item(record) for record in records],
            total=len(records),
        )

    def delete(self, analysis_id: str) -> bool:
        self.initialize()
        with self.sessions.begin() as session:
            record = session.get(AnalysisRecord, analysis_id)
            if record is None:
                return False
            feedback_records = session.scalars(
                select(AnalysisFeedbackRecord).where(
                    AnalysisFeedbackRecord.analysis_id == analysis_id
                )
            ).all()
            for feedback in feedback_records:
                session.delete(feedback)
            session.delete(record)
        return True


@lru_cache(maxsize=4)
def _store_for_path(database_path: str) -> AnalysisHistoryStore:
    return AnalysisHistoryStore(Path(database_path))


def get_history_store(settings: Settings | None = None) -> AnalysisHistoryStore:
    config = settings or get_settings()
    return _store_for_path(str(config.analysis_db_path))
