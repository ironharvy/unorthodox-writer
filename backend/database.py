"""Database connection and session management."""

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency — yields a DB session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _run_lightweight_migrations() -> None:
    """Additive, idempotent schema patches for SQLite.

    ``create_all`` only creates missing tables, never adds columns to existing
    ones, so a previously-created DB won't gain new columns. We add them here
    with ``ALTER TABLE ... ADD COLUMN`` (supported by SQLite) when absent.
    """
    inspector = inspect(engine)
    if "stories" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("stories")}
    if "max_words" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE stories ADD COLUMN max_words INTEGER NOT NULL DEFAULT 200"))


def init_db():
    """Create all tables and apply lightweight migrations. Call on startup."""
    from models import User, Story  # noqa: F401 — ensure models are imported
    Base.metadata.create_all(bind=engine)
    _run_lightweight_migrations()
