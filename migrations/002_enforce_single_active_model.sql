CREATE UNIQUE INDEX uq_models_single_active
ON models (is_active)
WHERE is_active = true;
