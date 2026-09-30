from datetime import date
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import Connection, func, insert, select, update
from sqlalchemy.sql import Select

from database.schema import energy_predictions_table, models_table

PredictionOrder = Literal["target_date", "created_desc"]


class ModelAmbiguousError(RuntimeError):
    """Raised when a model lookup matches more than one database row."""


class ModelRepository:
    def create(
        self,
        connection: Connection,
        *,
        name: str,
        version: str,
        horizon: int,
        is_active: bool = False,
    ) -> UUID:
        model_id = uuid4()
        connection.execute(
            insert(models_table).values(
                id=model_id,
                name=name,
                version=version,
                horizon=horizon,
                is_active=is_active,
            )
        )
        return model_id

    def get(self, connection: Connection, model_id: UUID) -> dict[str, object] | None:
        result = connection.execute(select(models_table).where(models_table.c.id == model_id))
        return result.mappings().one_or_none()

    def get_active(self, connection: Connection) -> list[dict[str, object]]:
        result = connection.execute(select(models_table).where(models_table.c.is_active.is_(True)))
        return list(result.mappings())

    def get_by_identity(
        self,
        connection: Connection,
        *,
        name: str,
        version: str,
    ) -> dict[str, object] | None:
        result = connection.execute(
            select(models_table).where(
                models_table.c.name == name,
                models_table.c.version == version,
            )
        )
        return result.mappings().one_or_none()

    def get_by_version(
        self, connection: Connection, version: str, *, name: str
    ) -> dict[str, object] | None:
        """Return the model with this name and version; raise if several rows match."""
        result = connection.execute(
            select(models_table).where(
                models_table.c.name == name,
                models_table.c.version == version,
            )
        )
        rows = result.mappings().all()
        if len(rows) > 1:
            raise ModelAmbiguousError(
                f"Model {name} version {version} matches {len(rows)} database rows"
            )
        return rows[0] if rows else None

    def activate(self, connection: Connection, model_id: UUID) -> None:
        """Backward-compatible safe activation; use promotion semantics."""
        self.promote(connection, model_id)

    def promote(self, connection: Connection, model_id: UUID) -> None:
        """Atomically make one existing model the sole active model."""
        # Lock every model row so concurrent promotions serialize.  The caller's
        # ``engine.begin()`` commits both updates as one database transaction.
        connection.execute(select(models_table.c.id).with_for_update())
        if self.get(connection, model_id) is None:
            raise ValueError("Cannot promote a model that does not exist")
        connection.execute(
            update(models_table)
            .where(models_table.c.is_active.is_(True), models_table.c.id != model_id)
            .values(is_active=False)
        )
        connection.execute(
            update(models_table).where(models_table.c.id == model_id).values(is_active=True)
        )


class EnergyPredictionRepository:
    def create(
        self,
        connection: Connection,
        *,
        target_date: date,
        predicted_demand_kwh: float,
        actual_demand_kwh: float | None,
        model_id: UUID,
    ) -> UUID:
        prediction_id = uuid4()
        connection.execute(
            insert(energy_predictions_table).values(
                id=prediction_id,
                target_date=target_date,
                predicted_demand_kwh=predicted_demand_kwh,
                actual_demand_kwh=actual_demand_kwh,
                model_id=model_id,
            )
        )
        return prediction_id

    def get(self, connection: Connection, prediction_id: UUID) -> dict[str, object] | None:
        result = connection.execute(
            select(energy_predictions_table).where(energy_predictions_table.c.id == prediction_id)
        )
        return result.mappings().one_or_none()

    def list(
        self,
        connection: Connection,
        *,
        start_date: date | None,
        end_date: date | None,
        page: int,
        page_size: int,
        order: PredictionOrder = "target_date",
    ) -> tuple[list[dict[str, object]], int]:
        statement: Select[tuple[object]] = select(energy_predictions_table)
        if start_date is not None:
            statement = statement.where(energy_predictions_table.c.target_date >= start_date)
        if end_date is not None:
            statement = statement.where(energy_predictions_table.c.target_date <= end_date)
        total = connection.execute(
            select(func.count()).select_from(statement.subquery())
        ).scalar_one()
        columns = energy_predictions_table.c
        if order == "created_desc":
            statement = statement.order_by(
                columns.created_at.desc(), columns.target_date.desc(), columns.id.desc()
            )
        else:
            statement = statement.order_by(columns.target_date.asc())
        statement = statement.offset((page - 1) * page_size).limit(page_size)
        result = connection.execute(statement)
        return list(result.mappings()), total
