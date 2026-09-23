CREATE TABLE models (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    horizon INTEGER NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_models_name_version UNIQUE (name, version)
);

CREATE TABLE energy_predictions (
    id UUID PRIMARY KEY,
    target_date DATE NOT NULL,
    predicted_demand_kwh DOUBLE PRECISION NOT NULL,
    actual_demand_kwh DOUBLE PRECISION NULL,
    model_id UUID NOT NULL REFERENCES models(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_energy_predictions_target_model UNIQUE (target_date, model_id)
);
