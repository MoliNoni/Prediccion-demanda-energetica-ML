from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Double,
    ForeignKey,
    Integer,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)

metadata = MetaData()

models_table = Table(
    "models",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("name", Text, nullable=False),
    Column("version", Text, nullable=False),
    Column("horizon", Integer, nullable=False),
    Column("is_active", Boolean, nullable=False, server_default="false"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("name", "version", name="uq_models_name_version"),
)

energy_predictions_table = Table(
    "energy_predictions",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("target_date", Date, nullable=False),
    Column("predicted_demand_kwh", Double, nullable=False),
    Column("actual_demand_kwh", Double, nullable=True),
    Column("model_id", Uuid(as_uuid=True), ForeignKey("models.id"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("target_date", "model_id", name="uq_energy_predictions_target_model"),
)
