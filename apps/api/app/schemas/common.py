from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class MessageResponse(ApiModel):
    message: str


class HealthResponse(ApiModel):
    status: str
