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
        Company(name="Great Eastern", short_name="GE", adapter_name="great_eastern", portal_url="https://www.greateasternlife.com/my", is_active=True),
        Company(name="Allianz Malaysia", short_name="Allianz", adapter_name="allianz", portal_url="https://www.allianz.com.my", is_active=True),
        Company(name="Zurich Malaysia", short_name="Zurich", adapter_name="zurich", portal_url="https://www.zurich.com.my", is_active=True),
        Company(name="AIA Malaysia", short_name="AIA", adapter_name="aia", portal_url="https://www.aia.com.my", is_active=True),
        Company(name="Etiqa Malaysia", short_name="Etiqa", adapter_name="etiqa", portal_url="https://www.etiqa.com.my", is_active=True),
        Company(name="Prudential Malaysia", short_name="Prudential", adapter_name="prudential", portal_url="https://www.prudential.com.my", is_active=True),
        Company(name="Tokio Marine", short_name="Tokio Marine", adapter_name="tokio_marine", portal_url="https://www.tokiomarine.com.my", is_active=True),
        Company(name="AXA Malaysia", short_name="AXA", adapter_name="axa", portal_url="https://www.axa.com.my", is_active=True),
        Company(name="Hong Leong Assurance", short_name="HLA", adapter_name="hla", portal_url="https://www.hla.com.my", is_active=True),
        Company(name="Takaful Malaysia", short_name="Takaful", adapter_name="takaful", portal_url="https://www.takaful-malaysia.com.my", is_active=True),
        Company(name="MSIG Malaysia", short_name="MSIG", adapter_name="msig", portal_url="https://www.msig.com.my", is_active=True),
        Company(name="Liberty General Insurance", short_name="Liberty", adapter_name="liberty", portal_url="https://www.libertygeneral.com.my", is_active=True),
        Company(name="Berjaya Sompo Insurance", short_name="Sompo", adapter_name="berjaya_sompo", portal_url="https://www.berjayasompo.com.my", is_active=True),
        Company(name="RHB Insurance", short_name="RHB", adapter_name="rhb", portal_url="https://www.rhbgroup.com/insurance", is_active=True),
        Company(name="MCIS Insurance", short_name="MCIS", adapter_name="mcis", portal_url="https://www.mcis.com.my", is_active=True),
        Company(name="Generali Malaysia", short_name="Generali", adapter_name="generali", portal_url="https://www.generali.com.my", is_active=True),
        Company(name="Chubb Insurance Malaysia", short_name="Chubb", adapter_name="chubb", portal_url="https://www.chubb.com/my", is_active=True),
        Company(name="AIG Malaysia", short_name="AIG", adapter_name="aig", portal_url="https://www.aig.com.my", is_active=True),
        Company(name="AmMetLife Insurance", short_name="AmMetLife", adapter_name="ammetlife", portal_url="https://www.ammetlife.com", is_active=True),
        Company(name="Sun Life Malaysia", short_name="Sun Life", adapter_name="sunlife", portal_url="https://www.sunlifemalaysia.com", is_active=True),
        Company(name="Manulife Insurance Malaysia", short_name="Manulife", adapter_name="manulife", portal_url="https://www.manulife.com.my", is_active=True),
        Company(name="OAC (Overseas Assurance Corp)", short_name="OAC", adapter_name="oac", portal_url="https://www.oac.com.my", is_active=True),
    ]
    session.add_all(defaults)
    session.commit()


def ensure_portals(session):
    """Create a default Portal for every company (idempotent).

    Extracts login_url/base_url from YAML profile when available.
    profile_state:
        READY        — has YAML automation profile
        UNCONFIGURED — no profile yet (login_url may be empty)
    """
    from .models import Company, Portal

    companies = session.query(Company).all()
    created = 0
    for c in companies:
        # Skip if company already has a portal
        if session.query(Portal).filter(Portal.company_id == c.id).count() > 0:
            continue

        login_url = ""
        base_url = ""
        profile_path = None
        profile_state = "UNCONFIGURED"

        if c.adapter_name:
            try:
                from src.portal.mapping import PORTALS_DIR, load_portal_mapping

                yaml_path = PORTALS_DIR / f"{c.adapter_name}.yaml"
                if yaml_path.exists():
                    mapping = load_portal_mapping(c.adapter_name)
                    if mapping:
                        login_url = mapping.login_url
                        base_url = mapping.base_url
                        profile_path = str(yaml_path)
                        profile_state = "READY"
            except Exception:
                pass

        portal = Portal(
            company_id=c.id,
            name=f"{c.short_name} Portal",
            login_url=login_url or None,
            base_url=base_url or None,
            profile_path=profile_path,
            profile_state=profile_state,
            is_default=True,
        )
        session.add(portal)
        created += 1

    if created:
        session.commit()
    return created
