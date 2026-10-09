"""Typed request envelopes; domain dicts keep flowing to existing validators."""
from __future__ import annotations

from datetime import date, date as _date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator


class Envelope(BaseModel):
    model_config = ConfigDict(extra='ignore')


class RevisionedValue(Envelope):
    value: dict = {}
    revision: int | None = Field(None, ge=0)


class RevisionedRecord(Envelope):
    record: dict = {}
    revision: int | None = Field(None, ge=0)


class RecordRemoval(Envelope):
    id: str = Field(min_length=1, max_length=150)
    revision: int | None = Field(None, ge=0)


class ReviewRequest(Envelope):
    day: date | None = None


class DecisionRequest(Envelope):
    decision: str = Field(min_length=1, max_length=40)
    day: date | None = None


class ProviderConfiguration(Envelope):
    credentials: dict | None = None
    enabled: StrictBool = True


class ImportRequest(Envelope):
    format: Literal['csv', 'gpx', 'fit', 'manual']
    content: str | dict
    filename: str = Field('import', max_length=200)


class ReconcileRequest(Envelope):
    record_id: str | None = None
    id: str | None = None
    action: str
    other_id: str | None = None

    @model_validator(mode='after')
    def _require_identifier(self):
        if not self.record_id and not self.id:
            raise ValueError('Informe o registro a reconciliar.')
        return self


class DayReviewRequest(Envelope):
    notes: str = ''


class AssistantRequest(Envelope):
    question: str
    day: date | None = None
    days: int = 14
    period: str = 'days'
    start: date | None = None
    end: date | None = None
    manual_response: str | None = None
    include_medical: StrictBool = False
    fingerprint: str | None = None
    conversation_id: str | None = None
    message_ids: list[str] = []


class DocumentUpload(Envelope):
    filename: str = Field(max_length=200)
    content: str
    label: str | None = None
    date: _date | None = None


class DocumentExtraction(Envelope):
    use_ai: StrictBool


class DocumentReview(Envelope):
    observations: list


class PlanningRecord(Envelope):
    record: dict


class RecipeRequest(Envelope):
    id: str | None = None
    title: str = ''
    servings: float = 1
    analysis: dict | None = None
    text: str = ''
