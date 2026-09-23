from config import Settings


def test_settings_default_to_development() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://user:pass@host/database",
    )

    assert settings.environment == "development"
    assert settings.log_level == "INFO"
