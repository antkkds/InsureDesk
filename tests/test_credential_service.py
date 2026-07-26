"""Tests for CredentialService — portal credential vault.

Tests the full lifecycle:
    store() → get() → verify() → list() → delete()

All tests use an in-memory SQLite database and a temporary
file-based master key (no keyring dependency in CI).
"""

import os
import tempfile
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.database.models import Base, PortalCredential
from src.runtime.credential_service import CredentialService, FALLBACK_KEY_FILE

# ── Fixtures ────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_keyring():
    """Prevent keyring from interfering with tests by pointing to a temp key file."""
    old_key_file = os.environ.get("INSURE_DESK_KEY_FILE")
    with tempfile.TemporaryDirectory() as tmp:
        test_key_file = os.path.join(tmp, ".master_key")
        os.environ["INSURE_DESK_KEY_FILE"] = test_key_file
        # Patch FALLBACK_KEY_FILE for the test
        import src.runtime.credential_service as cs
        old_fallback = cs.FALLBACK_KEY_FILE
        cs.FALLBACK_KEY_FILE = test_key_file
        yield
        cs.FALLBACK_KEY_FILE = old_fallback
        if old_key_file:
            os.environ["INSURE_DESK_KEY_FILE"] = old_key_file
        else:
            os.environ.pop("INSURE_DESK_KEY_FILE", None)


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


@pytest.fixture
def service(db_session):
    """Create a CredentialService with test database."""
    return CredentialService(db_session)


# ── Tests ────────────────────────────────────────────────────────


class TestCredentialService:
    """Credential Vault full lifecycle tests."""

    def test_store_and_retrieve(self, service):
        """Store credentials then retrieve them decrypted."""
        service.store("great_eastern", "agent01", "MyP@ss123!")
        cred = service.get("great_eastern")
        assert cred is not None
        assert cred.username == "agent01"
        assert cred.password == "MyP@ss123!"
        cred.clear()

    def test_get_nonexistent(self, service):
        """Getting credentials for an unconfigured portal returns None."""
        assert service.get("nonexistent_portal") is None

    def test_multiple_accounts(self, service):
        """Support multiple accounts per portal."""
        service.store("great_eastern", "agent01", "pass1", account_name="HQ")
        service.store("great_eastern", "agent02", "pass2", account_name="Sabah")
        service.store("allianz", "agent03", "pass3")

        hq = service.get("great_eastern", account_name="HQ")
        assert hq is not None
        assert hq.username == "agent01"
        assert hq.password == "pass1"

        sabah = service.get("great_eastern", account_name="Sabah")
        assert sabah is not None
        assert sabah.username == "agent02"

        default = service.get("great_eastern")
        # First stored should be default (HQ since it was first)
        assert default is not None

        hq.clear()
        sabah.clear()

    def test_list_credentials(self, service):
        """List returns metadata, not decrypted values."""
        service.store("great_eastern", "user1", "secret1")
        service.store("great_eastern", "user2", "secret2", account_name="Branch2")
        service.store("allianz", "user3", "secret3")

        ge_list = service.list(portal="great_eastern")
        assert len(ge_list) == 2
        for item in ge_list:
            assert item["portal"] == "great_eastern"
            assert "username" not in item  # should never contain plaintext
            assert "password" not in item

        all_list = service.list()
        assert len(all_list) == 3

    def test_list_portals(self, service):
        """list_portals returns distinct configured portals."""
        assert service.list_portals() == []
        service.store("great_eastern", "a", "b")
        assert service.list_portals() == ["great_eastern"]
        service.store("allianz", "c", "d")
        assert set(service.list_portals()) == {"great_eastern", "allianz"}

    def test_is_configured(self, service):
        """is_configured checks if portal has enabled credentials."""
        assert not service.is_configured("great_eastern")
        service.store("great_eastern", "u", "p")
        assert service.is_configured("great_eastern")
        assert not service.is_configured("allianz")

    def test_verify_valid(self, service):
        """verify passes for valid encrypted credentials."""
        service.store("great_eastern", "u", "p")
        assert service.verify("great_eastern") is True

    def test_verify_nonexistent(self, service):
        """verify fails for unconfigured portal."""
        assert service.verify("ghost_portal") is False

    def test_delete(self, service):
        """Delete removes credentials from database."""
        service.store("great_eastern", "u", "p")
        assert service.is_configured("great_eastern")

        creds = service.list(portal="great_eastern")
        assert len(creds) == 1

        service.delete(creds[0]["id"])
        assert not service.is_configured("great_eastern")
        assert service.get("great_eastern") is None

    def test_update_credentials(self, service):
        """Re-storing updates existing credentials."""
        service.store("great_eastern", "old_user", "old_pass")
        service.store("great_eastern", "new_user", "new_pass")

        cred = service.get("great_eastern")
        assert cred.username == "new_user"
        assert cred.password == "new_pass"
        cred.clear()

    def test_encryption_is_different(self, service, db_session):
        """Same plaintext produces different ciphertext each time (nonce)."""
        service.store("great_eastern", "same_user", "same_pass")
        stored_1 = db_session.query(PortalCredential).filter_by(
            portal="great_eastern"
        ).first()
        enc_1 = stored_1.encrypted_username

        # Store again with same values
        service.store("great_eastern", "same_user", "same_pass")
        stored_2 = db_session.query(PortalCredential).filter_by(
            portal="great_eastern"
        ).first()
        enc_2 = stored_2.encrypted_username

        # Each encryption should be different due to unique nonce
        assert enc_1 != enc_2

    def test_database_has_no_plaintext(self, service, db_session):
        """Database should never contain plaintext username or password."""
        service.store("great_eastern", "my_secret_user", "my_super_secret_pass")

        row = db_session.query(PortalCredential).filter_by(
            portal="great_eastern"
        ).first()
        assert row is not None
        # These should be base64-encoded encrypted blobs, not plaintext
        assert "my_secret_user" not in row.encrypted_username
        assert "my_super_secret_pass" not in row.encrypted_password

    def test_credential_clear_method(self, service):
        """Clear() should zero out sensitive fields."""
        cred = service.get("nonexistent")
        # Create a credential directly to test clear
        from src.runtime.credential_service import Credential
        c = Credential(portal="ge", account_name="default", username="u", password="p")
        assert c.username == "u"
        assert c.password == "p"
        c.clear()
        assert c.username == ""
        assert c.password == ""

    def test_master_key_persistence(self, db_session):
        """Master key persists between service instantiations."""
        s1 = CredentialService(db_session)
        s1.store("great_eastern", "u1", "p1")

        s2 = CredentialService(db_session)
        cred = s2.get("great_eastern")
        assert cred is not None
        assert cred.username == "u1"
        assert cred.password == "p1"
        cred.clear()

    def test_store_updates_timestamp(self, service):
        """Re-storing updates the timestamp."""
        from datetime import datetime, timezone

        service.store("great_eastern", "u", "p")
        creds = service.list(portal="great_eastern")
        first_updated = creds[0]["updated_at"]

        import time
        time.sleep(0.1)
        service.store("great_eastern", "new_u", "new_p")
        creds = service.list(portal="great_eastern")
        second_updated = creds[0]["updated_at"]

        assert second_updated != first_updated

    def test_verification_mismatch(self, service, db_session):
        """Verify returns False if database data is corrupted."""
        service.store("great_eastern", "u", "p")
        # Corrupt the encrypted data directly in DB
        row = db_session.query(PortalCredential).filter_by(
            portal="great_eastern"
        ).first()
        row.encrypted_username = "AAAA" + row.encrypted_username[4:]
        db_session.commit()

        assert service.verify("great_eastern") is False
