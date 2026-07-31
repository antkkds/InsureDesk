"""Tests: Portal Table & Company/Portal Separation (MVP).

Each company gets a default Portal row. login_url lives in DB
(Portal.login_url), YAML keeps automation selectors only.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPortalTable:
    """Company/Portal separation — each company gets a default Portal."""

    def _make_session(self, tmp_path):
        """Create an isolated DB session with seeded companies."""
        from src.database.db_manager import get_engine, get_session, init_db, seed_companies
        from src.database.models import Base

        db_path = tmp_path / "test.db"
        engine = get_engine(db_path)
        Base.metadata.create_all(engine)
        session = get_session(engine)
        seed_companies(session)
        return session

    def test_each_company_gets_default_portal(self, tmp_path):
        """ensure_portals creates one default portal per company."""
        from src.database.db_manager import ensure_portals
        from src.database.models import Company, Portal

        session = self._make_session(tmp_path)
        created = ensure_portals(session)

        companies = session.query(Company).count()
        portals = session.query(Portal).count()
        assert companies == 22
        assert portals == 22
        assert created == 22

        # Every company has exactly one default portal
        for c in session.query(Company).all():
            assert len(c.portals) == 1
            assert c.portals[0].is_default is True

    def test_great_eastern_portal_has_yaml_login_url(self, tmp_path):
        """GE portal extracts login_url/base_url from YAML -> READY."""
        from src.database.db_manager import ensure_portals
        from src.database.models import Company

        session = self._make_session(tmp_path)
        ensure_portals(session)

        ge = session.query(Company).filter(Company.short_name == "GE").first()
        portal = ge.portals[0]
        assert portal.login_url == "https://geglink.greateasterngeneral.com/geglink/userlogin.html"
        assert portal.base_url == "https://geglink.greateasterngeneral.com"
        assert portal.profile_state == "READY"
        assert portal.profile_path is not None

    def test_unknown_company_portal_unconfigured(self, tmp_path):
        """Companies without YAML stay UNCONFIGURED with no login_url."""
        from src.database.db_manager import ensure_portals
        from src.database.models import Company

        session = self._make_session(tmp_path)
        ensure_portals(session)

        # Tokio Marine has no YAML adapter
        tm = session.query(Company).filter(Company.short_name == "Tokio Marine").first()
        portal = tm.portals[0]
        assert portal.profile_state == "UNCONFIGURED"
        assert portal.login_url is None

    def test_ensure_portals_idempotent(self, tmp_path):
        """Running ensure_portals twice doesn't duplicate portals."""
        from src.database.db_manager import ensure_portals
        from src.database.models import Portal

        session = self._make_session(tmp_path)
        ensure_portals(session)
        second = ensure_portals(session)
        assert second == 0
        assert session.query(Portal).count() == 22

    def test_add_company_creates_company_and_portal(self, tmp_path):
        """Adding a company creates Company + default Portal (login_url saved)."""
        from src.database.db_manager import ensure_portals
        from src.database.models import Company, Portal

        session = self._make_session(tmp_path)
        ensure_portals(session)

        company = Company(name="ABC Insurance", short_name="ABC", portal_url="https://www.abc.com")
        session.add(company)
        session.flush()
        portal = Portal(
            company_id=company.id,
            name="ABC Portal",
            login_url="https://agent.abc.com/login",
            base_url="https://agent.abc.com",
            profile_state="UNCONFIGURED",
            is_default=True,
        )
        session.add(portal)
        session.commit()

        abc = session.query(Company).filter(Company.short_name == "ABC").first()
        assert abc is not None
        assert len(abc.portals) == 1
        assert abc.portals[0].login_url == "https://agent.abc.com/login"
        assert abc.portals[0].profile_state == "UNCONFIGURED"

    def test_start_url_priority_db_over_yaml(self, tmp_path):
        """PortalAdapter.start_url prefers DB login_url over YAML."""
        from src.database.db_manager import ensure_portals
        from src.database.models import Company
        from src.portals.great_eastern import GreatEasternAdapter

        session = self._make_session(tmp_path)
        ensure_portals(session)

        ge = session.query(Company).filter(Company.short_name == "GE").first()
        portal = ge.portals[0]

        # Simulate a user update to the login URL
        portal.login_url = "https://custom.geglink.example.com/login"
        session.commit()

        adapter = GreatEasternAdapter(login_url=portal.login_url)
        assert adapter.start_url == "https://custom.geglink.example.com/login"

    def test_start_url_yaml_fallback_when_no_db(self):
        """Without DB login_url, falls back to YAML login_url."""
        from src.portals.great_eastern import GreatEasternAdapter

        adapter = GreatEasternAdapter()
        assert adapter.start_url == "https://geglink.greateasterngeneral.com/geglink/userlogin.html"
