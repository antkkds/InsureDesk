"""Tests for Verifier formatting/truncation tolerance.

Discovered during live GEARS vertical slice (2026-08):
  - Angular strips dashes: '881212-14-5678' fills as '8812121456'
  - Angular truncates long IDs: 12-digit NRIC read-back is 10 digits
  - Verify must accept these WITHOUT accepting wrong/short values
"""
from __future__ import annotations

import pytest

from src.fill.verifier import Verifier


class TestVerifierFormatTolerance:
    def setup_method(self):
        self.v = Verifier()

    def test_truncation_with_dashes(self):
        """GEARS fills '881212-14-5678' as '8812121456' (10 of 12 digits)."""
        assert self.v._match("8812121456", "881212-14-5678") is True

    def test_case_and_space_normalization(self):
        assert self.v._match("wqk1234", "WQK 1234") is True

    def test_case_only(self):
        assert self.v._match("john", "John") is True

    def test_wrong_value_rejected(self):
        assert self.v._match("99999", "881212-14-5678") is False

    def test_too_short_rejected(self):
        """Prefix match requires >= 60% length — guards empty/short reads."""
        assert self.v._match("8", "881212-14-5678") is False
        assert self.v._match("", "881212-14-5678") is False
        assert self.v._match("M", "Male") is False

    def test_prefix_match_ok_when_long_enough(self):
        """Actual may be a prefix of expected when it retains enough chars."""
        assert self.v._match("88121214", "881212-14-5678") is True  # 8/12 = 67%
