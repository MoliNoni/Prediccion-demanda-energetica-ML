from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: Literal["ok"]


class ActiveModelResponse(BaseModel):
    id: UUID
    name: str
    version: str
    horizon: int
    is_active: bool
    created_at: datetime


class PredictionItem(BaseModel):
    id: UUID
    target_date: date
    predicted_demand_kwh: float
    actual_demand_kwh: float | None
    model_id: UUID
    created_at: datetime


class PredictionListResponse(BaseModel):
    items: list[PredictionItem]
    page: int
    page_size: int
    total: int


class DemandItem(BaseModel):
    date: date
    demand_kwh: float


class DemandListResponse(BaseModel):
    items: list[DemandItem]
    page: int
    page_size: int
    total: int


class PredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_date: date


class PredictionResponse(BaseModel):
    id: UUID
    target_date: date
    predicted_demand_kwh: float
    actual_demand_kwh: float | None
    model_id: UUID
    model_name: str
    model_version: str
    horizon: int
    created_at: datetime


class Pagination(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=30, ge=1, le=100)
