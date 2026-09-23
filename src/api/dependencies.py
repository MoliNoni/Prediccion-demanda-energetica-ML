from collections.abc import Generator

from sqlalchemy import Connection

from application.historical_demand import HistoricalDemandQuery
from application.prediction import PredictionService
from database.session import create_database_engine


def get_connection() -> Generator[Connection, None, None]:
    engine = create_database_engine()
    with engine.begin() as connection:
        yield connection


def get_historical_demand_query() -> HistoricalDemandQuery:
    return HistoricalDemandQuery()


def get_prediction_service() -> PredictionService:
    return PredictionService()
