from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Connection
from sqlalchemy.exc import SQLAlchemyError

from api.dependencies import get_connection, get_historical_demand_query, get_prediction_service
from api.schemas import (
    ActiveModelResponse,
    DemandListResponse,
    HealthResponse,
    PredictionListResponse,
    PredictionRequest,
    PredictionResponse,
)
from application.historical_demand import HistoricalDemandError, HistoricalDemandQuery
from application.prediction import (
    HistoricalDemandUnavailableError,
    InsufficientHistoryError,
    MultipleActiveModelsError,
    NoActiveModelError,
    PredictionAlreadyExistsError,
    PredictionService,
)
from database.repositories import EnergyPredictionRepository, ModelRepository
from models.serving import ServingArtifactUnavailableError

router = APIRouter()

PAGE = Annotated[int, Query(ge=1)]
PAGE_SIZE = Annotated[int, Query(ge=1, le=100)]
DATABASE_CONNECTION = Annotated[Connection, Depends(get_connection)]
HISTORICAL_QUERY = Annotated[HistoricalDemandQuery, Depends(get_historical_demand_query)]
PREDICTION_SERVICE = Annotated[PredictionService, Depends(get_prediction_service)]
UNAVAILABLE_INFERENCE = (
    "Prediction inference is not available because no serialized model artifact is configured."
)


def validate_date_range(start_date: date | None, end_date: date | None) -> None:
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail="start_date must be less than or equal to end_date",
        )


@router.get("/health", response_model=HealthResponse, tags=["operational"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/api/v1/models/active", response_model=ActiveModelResponse, tags=["models"])
def get_active_model(connection: DATABASE_CONNECTION) -> dict[str, object]:
    try:
        models = ModelRepository().get_active(connection)
    except SQLAlchemyError as error:
        raise HTTPException(status_code=500, detail="Database query failed") from error
    if not models:
        raise HTTPException(status_code=404, detail="No active model found")
    if len(models) > 1:
        raise HTTPException(status_code=500, detail="Multiple active models found")
    return models[0]


@router.get("/api/v1/predictions", response_model=PredictionListResponse, tags=["predictions"])
def list_predictions(
    connection: DATABASE_CONNECTION,
    start_date: date | None = None,
    end_date: date | None = None,
    page: PAGE = 1,
    page_size: PAGE_SIZE = 30,
) -> PredictionListResponse:
    validate_date_range(start_date, end_date)
    try:
        items, total = EnergyPredictionRepository().list(
            connection,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
        )
    except SQLAlchemyError as error:
        raise HTTPException(status_code=500, detail="Database query failed") from error
    return PredictionListResponse(items=items, page=page, page_size=page_size, total=total)


@router.get("/api/v1/demand", response_model=DemandListResponse, tags=["demand"])
def list_demand(
    query: HISTORICAL_QUERY,
    start_date: date | None = None,
    end_date: date | None = None,
    page: PAGE = 1,
    page_size: PAGE_SIZE = 30,
) -> DemandListResponse:
    validate_date_range(start_date, end_date)
    try:
        items, total = query.list(
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
        )
    except HistoricalDemandError as error:
        raise HTTPException(
            status_code=500,
            detail="Historical demand data is unavailable",
        ) from error
    return DemandListResponse(items=items, page=page, page_size=page_size, total=total)


@router.post(
    "/api/v1/predictions",
    response_model=PredictionResponse,
    status_code=201,
    tags=["predictions"],
)
def create_prediction(
    request: PredictionRequest,
    connection: DATABASE_CONNECTION,
    service: PREDICTION_SERVICE,
) -> PredictionResponse:
    try:
        return PredictionResponse(**service.predict(connection, request.target_date))
    except NoActiveModelError as error:
        raise HTTPException(status_code=404, detail="No active model found") from error
    except MultipleActiveModelsError as error:
        raise HTTPException(status_code=500, detail="Multiple active models found") from error
    except PredictionAlreadyExistsError as error:
        raise HTTPException(
            status_code=409,
            detail="A prediction already exists for this target_date and model_id",
        ) from error
    except InsufficientHistoryError as error:
        raise HTTPException(
            status_code=503,
            detail="Prediction inference is unavailable because historical demand is incomplete",
        ) from error
    except ServingArtifactUnavailableError as error:
        raise HTTPException(status_code=503, detail=UNAVAILABLE_INFERENCE) from error
    except HistoricalDemandUnavailableError as error:
        raise HTTPException(
            status_code=500,
            detail="Historical demand data is unavailable",
        ) from error
    except SQLAlchemyError as error:
        raise HTTPException(status_code=500, detail="Database query failed") from error
