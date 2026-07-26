"""Integration test: InsureDesk Bridge → UIP-AI Portfolio endpoints.

Tests the BridgeClient portfolio methods with mocked HTTP.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import requests


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def bridge():
    """Create a BridgeClient that appears connected."""
    from src.bridge.protocol import BridgeClient
    client = BridgeClient(base_url="http://test.local:8000", token="test-token")
    client.connected = True
    return client


# ── Sample policy data ────────────────────────────────────────────

SAMPLE_POLICIES = [
    {
        "parse_result": {
            "policy": {
                "company": "Great Eastern",
                "product_name": "Medical Shield",
                "premium": 2400.0,
            },
            "coverage": [{"name": "Hospital Room", "limit": "RM400", "status": "active"}],
            "exclusions": [],
            "summary": "Medical coverage from GE.",
        },
        "metadata": {
            "policy_id": "P001",
            "source": "agent_upload",
            "relationship": "sold_by_agent",
        },
    },
    {
        "parse_result": {
            "policy": {
                "company": "Allianz",
                "product_name": "Life Protect",
                "premium": 3600.0,
            },
            "coverage": [{"name": "Death Benefit", "limit": "RM500k", "status": "active"}],
            "exclusions": [],
            "summary": "Life insurance.",
        },
        "metadata": {
            "policy_id": "P002",
            "source": "customer_upload",
            "relationship": "customer_existing",
        },
    },
]


# ══════════════════════════════════════════════════════════════════
# Bridge Connection Tests
# ══════════════════════════════════════════════════════════════════

class TestBridgeConnection:
    """Verify bridge connection/disconnection."""

    def test_connect_success(self):
        """Successful health check = connected."""
        from src.bridge.protocol import BridgeClient

        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {"status": "ok"}

            client = BridgeClient()
            result = client.connect("test-token")

            assert result is True
            assert client.connected is True
            assert client.token == "test-token"

    def test_connect_failure(self):
        """Failed health check = not connected."""
        from src.bridge.protocol import BridgeClient

        with patch("requests.get") as mock_get:
            mock_get.side_effect = requests.RequestException("Connection failed")

            client = BridgeClient()
            result = client.connect("test-token")

            assert result is False
            assert client.connected is False

    def test_disconnect(self):
        """Disconnect clears token and session."""
        from src.bridge.protocol import BridgeClient

        client = BridgeClient()
        client.connected = True
        client.token = "test-token"
        client.session_id = "sess-1"

        client.disconnect()

        assert client.connected is False
        assert client.token == ""
        assert client.session_id is None

    def test_ping_connected(self):
        """Ping returns True when connected and server responds."""
        from src.bridge.protocol import BridgeClient

        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 200

            client = BridgeClient()
            client.connected = True
            client.token = "test-token"
            result = client.ping()

            assert result is True

    def test_ping_disconnected(self):
        """Ping returns False when disconnected."""
        from src.bridge.protocol import BridgeClient

        client = BridgeClient()
        result = client.ping()
        assert result is False


# ══════════════════════════════════════════════════════════════════
# Bridge Portfolio Methods
# ══════════════════════════════════════════════════════════════════

class TestBridgePortfolio:
    """Verify BridgeClient portfolio methods."""

    def test_build_portfolio_not_connected(self, bridge):
        """Not connected = None."""
        bridge.connected = False
        result = bridge.build_portfolio("C001", "John", [])
        assert result is None

    @patch("src.bridge.protocol.requests.post")
    def test_build_portfolio_success(self, mock_post, bridge):
        """Successful portfolio build returns data."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "customer_id": "C001",
            "customer_name": "John Tan",
            "total_policies": 2,
            "total_premium": 6000.0,
            "medical_policies": [],
            "life_policies": [],
            "motor_policies": [],
            "pa_policies": [],
            "travel_policies": [],
            "home_policies": [],
            "other_policies": [],
        }

        result = bridge.build_portfolio("C001", "John Tan", SAMPLE_POLICIES)

        assert result is not None
        assert result["customer_id"] == "C001"
        assert result["total_policies"] == 2
        assert result["total_premium"] == 6000.0

        # Verify correct endpoint called
        url = mock_post.call_args[0][0]
        assert "/v1/policy/portfolio/build" in url

    @patch("src.bridge.protocol.requests.post")
    def test_build_portfolio_failure(self, mock_post, bridge):
        """HTTP error = None."""
        mock_post.side_effect = requests.RequestException("Server error")

        result = bridge.build_portfolio("C001", "John", SAMPLE_POLICIES)
        assert result is None

    @patch("src.bridge.protocol.requests.post")
    def test_query_portfolio_success(self, mock_post, bridge):
        """Portfolio query returns answer."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "answer": "John's portfolio covers Medical (GE) and Life (Allianz)."
        }

        result = bridge.query_portfolio(
            "C001", "John Tan", SAMPLE_POLICIES, "我的保险怎么样？"
        )

        assert result is not None
        assert "Medical" in result
        assert "Life" in result

        # Verify correct endpoint
        url = mock_post.call_args[0][0]
        assert "/v1/policy/portfolio/query" in url

    @patch("src.bridge.protocol.requests.post")
    def test_query_portfolio_not_connected(self, mock_post, bridge):
        """Not connected = None."""
        bridge.connected = False
        result = bridge.query_portfolio("C001", "John", [], "test")
        assert result is None

    @patch("src.bridge.protocol.requests.post")
    def test_analyze_gaps_success(self, mock_post, bridge):
        """Gap analysis returns list of gaps."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "gaps": [
                {
                    "category": "Personal Accident",
                    "description": "No PA coverage",
                    "current_coverage": "None",
                    "gap_level": "medium",
                    "suggestion": "Consider PA insurance",
                }
            ]
        }

        result = bridge.analyze_gaps("C001", "John Tan", SAMPLE_POLICIES, customer_age=35)

        assert result is not None
        assert len(result) == 1
        assert result[0]["category"] == "Personal Accident"
        assert result[0]["gap_level"] == "medium"

        url = mock_post.call_args[0][0]
        assert "/v1/policy/portfolio/gaps" in url

    @patch("src.bridge.protocol.requests.post")
    def test_analyze_gaps_not_connected(self, mock_post, bridge):
        """Not connected = None."""
        bridge.connected = False
        result = bridge.analyze_gaps("C001", "John", [], 30)
        assert result is None


# ══════════════════════════════════════════════════════════════════
# Bridge Upload Policy
# ══════════════════════════════════════════════════════════════════

class TestBridgeUploadPolicy:
    """Verify upload_policy integration."""

    def test_upload_not_connected(self, bridge):
        """Not connected = None."""
        bridge.connected = False
        result = bridge.upload_policy("/tmp/test.pdf", "C001")
        assert result is None

    def test_upload_missing_file(self, bridge):
        """Missing file = None."""
        with patch("os.path.exists", return_value=False):
            result = bridge.upload_policy("/nonexistent.pdf", "C001")
            assert result is None

    @patch("src.bridge.protocol.requests.post")
    def test_upload_success(self, mock_post, bridge):
        """Successful upload returns parsed data."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "company": "Great Eastern",
            "policy_number": "GE-12345",
            "policy_type": "medical",
            "status": "active",
            "premium": "2400",
            "coverage": [{"name": "Hospital Room", "limit": "RM400"}],
            "summary": "Medical coverage",
        }

        with patch("os.path.exists", return_value=True):
            with patch("builtins.open") as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = b"test pdf content"
                result = bridge.upload_policy("/tmp/test.pdf", "C001")

        assert result is not None
        assert result["company"] == "Great Eastern"
        assert result["policy_number"] == "GE-12345"
