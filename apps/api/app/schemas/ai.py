from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from app.models.enums import AIRequestStatus, AISourceType, AITaskType
from app.schemas.common import ApiModel

AIOptionKey = Annotated[
    str,
    Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$"),
]
AIOptionValue = (
    Annotated[str, Field(max_length=500)]
    | Annotated[int, Field(ge=-1_000_000, le=1_000_000)]
    | bool
)


class AISourceInput(ApiModel):
    source_type: AISourceType
    source_id: uuid.UUID


class AIGenerateRequest(ApiModel):
    organization_id: uuid.UUID
    task_type: AITaskType
    sources: list[AISourceInput] = Field(min_length=1, max_length=20)
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    options: dict[AIOptionKey, AIOptionValue] = Field(default_factory=dict, max_length=10)


class AIShortcutRequest(ApiModel):
    organization_id: uuid.UUID
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")


BoundedText = Annotated[str, Field(max_length=1000)]


class AIContent(ApiModel):
    title: str = Field(max_length=200)
    summary: str = Field(max_length=2000)
    details: list[BoundedText] = Field(max_length=20)
    caveats: list[BoundedText] = Field(max_length=10)
    source_references: list[Annotated[str, Field(max_length=300)]] = Field(max_length=20)
    draft_only: bool = True


class AIRequestResponse(ApiModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    requested_by_user_id: uuid.UUID
    task_type: AITaskType
    status: AIRequestStatus
    idempotency_key: str
    provider_key: str
    prompt_key: str
    prompt_version: int
    context_hash: str
    request_fingerprint: str
    response_schema_version: int
    model_key: str
    error_code: str | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
    source_type: AISourceType
    source_id: uuid.UUID
    source_version: int
    source_staleness: Literal["current", "stale", "source_missing"]
    content: AIContent | None = None


class AIRequestListResponse(ApiModel):
    items: list[AIRequestResponse]
    total: int
    page: int
    page_size: int
