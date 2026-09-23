from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from config import get_settings


def create_database_engine() -> Engine:
    """Create the database engine; connections are opened only by callers."""
    settings = get_settings()
    database_url = settings.database_url
    if database_url.startswith("postgresql://"):
        database_url = "postgresql+psycopg://" + database_url[len("postgresql://") :]
    return create_engine(database_url, pool_pre_ping=True)
