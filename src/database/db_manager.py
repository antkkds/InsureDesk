"""InsureDesk — Database manager (SQLite + SQLAlchemy)."""

import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from .models import Base


# Default data directory (user's home)
DATA_DIR = Path.home() / "InsureDesk"
DB_PATH = DATA_DIR / "insuredesk.db"


def get_engine(db_path=None):
    """Create and return the SQLAlchemy engine."""
    if db_path is None:
        db_path = DB_PATH
    # Ensure directory exists
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}")
    return engine


def init_db(engine=None):
    """Initialize the database (create tables if not exist)."""
    if engine is None:
        engine = get_engine()
    Base.metadata.create_all(engine)
    return engine


def get_session(engine=None):
    """Get a new SQLAlchemy session."""
    if engine is None:
        engine = get_engine()
    Session = sessionmaker(bind=engine)
    return Session()


def seed_companies(session):
    """Seed default insurance companies if table is empty."""
    from .models import Company

    if session.query(Company).count() > 0:
        return

    defaults = [
        Company(name="Great Eastern", short_name="GE", adapter_name="great_eastern", is_active=True),
        Company(name="Allianz Malaysia", short_name="Allianz", adapter_name="allianz", is_active=True),
        Company(name="Zurich Malaysia", short_name="Zurich", adapter_name="zurich", is_active=True),
        Company(name="AIA Malaysia", short_name="AIA", adapter_name="aia", is_active=True),
        Company(name="Etiqa Malaysia", short_name="Etiqa", adapter_name="etiqa", is_active=True),
        Company(name="Prudential Malaysia", short_name="Prudential", adapter_name="prudential", is_active=True),
        Company(name="Tokio Marine", short_name="Tokio Marine", adapter_name="tokio_marine", is_active=True),
        Company(name="AXA Malaysia", short_name="AXA", adapter_name="axa", is_active=True),
        Company(name="Hong Leong Assurance", short_name="HLA", adapter_name="hla", is_active=True),
        Company(name="Takaful Malaysia", short_name="Takaful", adapter_name="takaful", is_active=True),
    ]
    session.add_all(defaults)
    session.commit()
