from dataclasses import dataclass

TARGET_COLUMN = "target_h1"
DATE_COLUMNS = ("reference_date", "target_date")


@dataclass(frozen=True)
class FeatureContract:
    """Versioned, ordered feature contract for one H+1 model family."""

    name: str
    version: str
    predictor_columns: tuple[str, ...]

    @property
    def feature_columns(self) -> tuple[str, ...]:
        return (*DATE_COLUMNS, *self.predictor_columns, TARGET_COLUMN)


V1_PREDICTOR_COLUMNS = (
    "lag_1",
    "lag_7",
    "lag_14",
    "lag_28",
    "rolling_mean_7",
    "rolling_std_7",
    "rolling_mean_14",
    "rolling_std_14",
    "rolling_mean_28",
    "rolling_std_28",
    "weekday",
    "day_of_month",
    "month",
    "iso_week",
    "day_of_year",
    "weekend",
    "weekday_sin",
    "weekday_cos",
    "month_sin",
    "month_cos",
    "day_of_year_sin",
    "day_of_year_cos",
)

V2_ADDITIONAL_PREDICTOR_COLUMNS = (
    "demand_at_reference_date",
    "lag_2",
    "lag_3",
    "rolling_mean_3_including_reference",
    "rolling_std_3_including_reference",
)

FEATURE_CONTRACT_V1 = FeatureContract(
    name="energy_demand_h1",
    version="v1",
    predictor_columns=V1_PREDICTOR_COLUMNS,
)
FEATURE_CONTRACT_V2 = FeatureContract(
    name="energy_demand_h1",
    version="v2",
    predictor_columns=(*V1_PREDICTOR_COLUMNS, *V2_ADDITIONAL_PREDICTOR_COLUMNS),
)
