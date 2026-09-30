from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import Connection
from sqlalchemy.exc import IntegrityError

from application.historical_demand import HISTORICAL_DEMAND_PATH
from database.repositories import EnergyPredictionRepository, ModelRepository
from features.pipeline import FeaturePreparationError
from ingestion.constants import EXPECTED_COLUMNS, TARGET_COLUMN
from models.serving import MlflowModelLoader
from models.serving_registry import ServingModelRegistry


class NoActiveModelError(RuntimeError):
    """Raised when serving has no active database model."""


class MultipleActiveModelsError(RuntimeError):
    """Raised when database integrity permits multiple active models."""


class PredictionAlreadyExistsError(RuntimeError):
    """Raised when the prediction uniqueness constraint is violated."""


class PredictionDataUnavailableError(RuntimeError):
    """Raised when historical data cannot support online features."""


class HistoricalDemandUnavailableError(PredictionDataUnavailableError):
    """Raised when the approved historical source cannot be read."""


class InsufficientHistoryError(PredictionDataUnavailableError):
    """Raised when the source cannot provide complete H+1 features."""


class ModelNotRegisteredError(RuntimeError):
    """Raised when a requested model version has no registered database row."""


class PredictionService:
    def __init__(
        self,
        *,
        history_path: Path = HISTORICAL_DEMAND_PATH,
        model_loader: MlflowModelLoader | None = None,
        serving_registry: ServingModelRegistry | None = None,
    ) -> None:
        self.history_path = history_path
        self.serving_registry = serving_registry or ServingModelRegistry(v1_loader=model_loader)

    def predict(
        self, connection: Connection, target_date: date, model_version: str | None = None
    ) -> dict[str, Any]:
        """Predict with the active model, or with the registered ``model_version`` if given."""
        active_model = self._select_model(connection, model_version)
        model, metadata, feature_builder = self.serving_registry.load(active_model)

        frame = self._read_history()
        try:
            feature_row = feature_builder(frame, target_date)
        except FeaturePreparationError as error:
            raise InsufficientHistoryError(str(error)) from error
        predictor_columns = metadata["predictor_columns"]
        predicted_demand = float(model.predict(feature_row.loc[:, predictor_columns])[0])
        actual_demand = self._actual_demand(frame, target_date)

        try:
            prediction_id = EnergyPredictionRepository().create(
                connection,
                target_date=target_date,
                predicted_demand_kwh=predicted_demand,
                actual_demand_kwh=actual_demand,
                model_id=active_model["id"],
            )
        except IntegrityError as error:
            raise PredictionAlreadyExistsError from error
        stored_prediction = EnergyPredictionRepository().get(connection, prediction_id)
        if stored_prediction is None:
            raise RuntimeError("Created prediction could not be loaded")
        return {
            **stored_prediction,
            "model_name": active_model["name"],
            "model_version": active_model["version"],
            "horizon": active_model["horizon"],
        }

    @staticmethod
    def _select_model(connection: Connection, model_version: str | None) -> dict[str, object]:
        if model_version is not None:
            requested = ModelRepository().get_by_version(connection, model_version)
            if requested is None:
                raise ModelNotRegisteredError(f"Model version {model_version} is not registered")
            return requested
        active_models = ModelRepository().get_active(connection)
        if not active_models:
            raise NoActiveModelError
        if len(active_models) > 1:
            raise MultipleActiveModelsError
        return active_models[0]

    def _read_history(self) -> pd.DataFrame:
        try:
            return pd.read_parquet(self.history_path, columns=list(EXPECTED_COLUMNS))
        except (FileNotFoundError, OSError, ValueError) as error:
            raise HistoricalDemandUnavailableError(
                "Historical demand data is unavailable"
            ) from error

    @staticmethod
    def _actual_demand(frame: pd.DataFrame, target_date: date) -> float | None:
        dates = pd.to_datetime(frame["Fecha"], errors="raise").dt.date
        matches = frame.loc[dates == target_date, TARGET_COLUMN]
        if matches.empty or pd.isna(matches.iloc[0]):
            return None
        return float(matches.iloc[0])
