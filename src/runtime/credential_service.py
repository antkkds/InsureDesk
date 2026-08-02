"""CredentialService — Secure portal credential management.

Architecture:
    CredentialService
        │
        ├── encrypt() / decrypt()  (AES-256-GCM)
        ├── store() / get() / delete() / list()
        │
        ├── Master Key → keyring (OS Secret Store)
        │       Windows: Credential Manager
        │       Linux:   Secret Service (libsecret)
        │       macOS:   Keychain
        │
        └── PortalCredential table → encrypted blobs only

Design principles:
    - Database NEVER sees plaintext usernames or passwords
    - Master key NEVER stored in database or config files
    - Credentials decrypted ONLY in memory, cleared after use
    - BrowserSession never knows where credentials come from
    - Supports multi-account per portal (e.g., "Anthony HQ", "Anthony Sabah")
"""

import base64
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session as DbSession

from src.database.models import PortalCredential

SERVICE_NAME = "InsureDesk"
KEYRING_KEY = "credential_master_key"

try:
    import keyring
    HAS_KEYRING = True
except Exception:
    HAS_KEYRING = False

# Fallback: file-based master key when keyring unavailable (dev/test only)
FALLBACK_KEY_FILE = os.path.expanduser("~/.insuredesk/.master_key")


@dataclass
class Credential:
    """Decrypted portal credential — short-lived, keep in memory only."""
    portal: str
    account_name: str
    username: str
    password: str

    def clear(self):
        """Securely clear sensitive data from memory."""
        self.username = ""
        self.password = ""
        self.portal = ""
        self.account_name = ""


class CredentialService:
    """Credential Vault — encrypts, stores, and serves portal credentials.

    Usage:
        service = CredentialService(db_session)
        service.store("great_eastern", "default", "agent01", "secret123")
        cred = service.get("great_eastern")
        session.login(cred.username, cred.password)
        cred.clear()  # ← immediately after use
    """

    def __init__(self, db: DbSession):
        self._db = db
        self._key: Optional[bytes] = None

    # ── Public API ────────────────────────────────────────────────

    def store(
        self,
        portal: str,
        username: str,
        password: str,
        account_name: str = "default",
        is_default: bool = False,
    ) -> PortalCredential:
        """Encrypt and store portal credentials."""
        enc_user = self._encrypt(username)
        enc_pass = self._encrypt(password)

        # If this is the first credential for this portal, make it default
        existing = self._db.query(PortalCredential).filter_by(
            portal=portal, account_name=account_name
        ).first()
        if existing:
            existing.encrypted_username = enc_user
            existing.encrypted_password = enc_pass
            existing.is_default = is_default
            existing.updated_at = datetime.utcnow()
            obj = existing
        else:
            obj = PortalCredential(
                portal=portal,
                account_name=account_name,
                encrypted_username=enc_user,
                encrypted_password=enc_pass,
                is_default=is_default or not self._has_any(portal),
            )
            self._db.add(obj)

        self._db.commit()
        return obj

    def get(self, portal: str, account_name: str = None) -> Optional[Credential]:
        """Retrieve and decrypt credentials for a portal account.

        If account_name is None, returns the default credential for the portal.
        """
        q = self._db.query(PortalCredential).filter_by(
            portal=portal, enabled=True
        )
        if account_name:
            q = q.filter_by(account_name=account_name)
        else:
            q = q.order_by(PortalCredential.is_default.desc())
        cred = q.first()
        if not cred:
            return None

        try:
            username = self._decrypt(cred.encrypted_username)
            password = self._decrypt(cred.encrypted_password)
        except Exception:
            return None

        # Mark as used
        cred.last_used = datetime.utcnow()
        self._db.commit()

        return Credential(
            portal=cred.portal,
            account_name=cred.account_name,
            username=username,
            password=password,
        )

    def list(self, portal: Optional[str] = None) -> list[dict]:
        """List stored credential metadata (NO decrypted values)."""
        q = self._db.query(PortalCredential)
        if portal:
            q = q.filter_by(portal=portal)
        results = []
        for c in q.order_by(PortalCredential.portal, PortalCredential.account_name).all():
            results.append({
                "id": c.id,
                "portal": c.portal,
                "account_name": c.account_name,
                "is_default": c.is_default,
                "enabled": c.enabled,
                "last_verified": c.last_verified.isoformat() if c.last_verified else None,
                "last_used": c.last_used.isoformat() if c.last_used else None,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            })
        return results

    def list_portals(self):
        """Return distinct portal names that have credentials configured."""
        rows = self._db.query(PortalCredential.portal).filter(
            PortalCredential.enabled == True
        ).distinct().all()
        return [r[0] for r in rows]

    def delete(self, credential_id: str) -> bool:
        """Delete a credential entry."""
        cred = self._db.get(PortalCredential, credential_id)
        if cred:
            self._db.delete(cred)
            self._db.commit()
            return True
        return False

    def verify(self, portal: str, account_name: str = None) -> bool:
        """Test that stored credentials can be decrypted successfully.

        If account_name is None (or the named account doesn't exist),
        falls back to the portal's default/any credential.

        Note: This is NOT a portal login test — it only verifies that
        the encrypted data hasn't been corrupted and the master key works.
        """
        try:
            cred = self.get(portal, account_name)
            if not cred and account_name:
                # Named account not found — try default/any for this portal
                cred = self.get(portal, None)
            if cred:
                cred.clear()
                return True
            return False
        except Exception:
            return False

    def is_configured(self, portal: str) -> bool:
        """Check if any enabled credential exists for this portal."""
        return self._db.query(PortalCredential).filter_by(
            portal=portal, enabled=True
        ).first() is not None

    # ── Master Key Management ────────────────────────────────────

    def _get_master_key(self) -> bytes:
        """Get or create the AES-256 master key from OS secret store."""
        if self._key is not None:
            return self._key

        key_b64 = None
        if HAS_KEYRING:
            try:
                key_b64 = keyring.get_password(SERVICE_NAME, KEYRING_KEY)
            except Exception:
                pass

        if not key_b64:
            # Try fallback file (dev environments without keyring daemon)
            if os.path.exists(FALLBACK_KEY_FILE):
                with open(FALLBACK_KEY_FILE) as f:
                    key_b64 = f.read().strip()

        if not key_b64:
            # Generate new master key
            key = os.urandom(32)  # AES-256
            key_b64 = base64.b64encode(key).decode()

            if HAS_KEYRING:
                try:
                    keyring.set_password(SERVICE_NAME, KEYRING_KEY, key_b64)
                except Exception:
                    self._write_fallback_key(key_b64)
            else:
                self._write_fallback_key(key_b64)

        self._key = base64.b64decode(key_b64)
        return self._key

    def _write_fallback_key(self, key_b64: str):
        """Write master key to file as fallback (dev only)."""
        os.makedirs(os.path.dirname(FALLBACK_KEY_FILE), exist_ok=True)
        with open(FALLBACK_KEY_FILE, "w") as f:
            f.write(key_b64)
        os.chmod(FALLBACK_KEY_FILE, 0o600)

    # ── Encryption (AES-256-GCM) ──────────────────────────────────

    def _encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext with AES-256-GCM. Returns base64(nonce + ciphertext)."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        key = self._get_master_key()
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return base64.b64encode(nonce + ct).decode("utf-8")

    def _decrypt(self, ciphertext_b64: str) -> str:
        """Decrypt base64(nonce + ciphertext) with AES-256-GCM."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        key = self._get_master_key()
        data = base64.b64decode(ciphertext_b64)
        nonce, ct = data[:12], data[12:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ct, None).decode("utf-8")

    # ── Helpers ──────────────────────────────────────────────────

    def _has_any(self, portal: str) -> bool:
        return self._db.query(PortalCredential).filter_by(
            portal=portal
        ).first() is not None
