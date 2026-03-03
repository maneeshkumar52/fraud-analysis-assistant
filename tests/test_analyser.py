"""
Tests for fraud-analysis-assistant components.

All tests run without Azure credentials by relying on MOCK_MODE=true and
the in-memory fallback data baked into RiskProfileCache and EventHubProcessor.
"""

import pytest
import os

# Force mock mode so no Azure resources are needed
os.environ.setdefault("MOCK_MODE", "true")

from src.models import (
    FlaggedTransaction,
    CustomerRiskProfile,
    RiskLevel,
)
from src.pattern_matcher import PatternMatcher
from src.risk_profile import RiskProfileCache
from src.event_processor import EventHubProcessor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def normal_transaction() -> FlaggedTransaction:
    """A transaction well within the customer's normal behaviour."""
    return FlaggedTransaction(
        transaction_id="TXN-TEST-001",
        customer_id="CUST-001",
        amount=50.0,
        currency="GBP",
        merchant_name="Tesco",
        merchant_category="Grocery",
        location_country="GB",
        location_city="London",
        timestamp="2025-01-22T12:00:00Z",
        flag_reason="Velocity check",
        flag_score=0.30,
    )


@pytest.fixture
def high_amount_transaction() -> FlaggedTransaction:
    """A transaction whose amount is more than 2x the customer's typical max."""
    return FlaggedTransaction(
        transaction_id="TXN-TEST-002",
        customer_id="CUST-001",
        amount=5000.0,  # CUST-001 typical max is £200 → 25x over
        currency="GBP",
        merchant_name="ElectroMart",
        merchant_category="Electronics",
        location_country="GB",
        location_city="London",
        timestamp="2025-01-22T12:00:00Z",
        flag_reason="Amount significantly above typical range",
        flag_score=0.85,
    )


@pytest.fixture
def low_risk_profile() -> CustomerRiskProfile:
    """Risk profile matching CUST-001 from mock data."""
    return CustomerRiskProfile(
        customer_id="CUST-001",
        risk_score=15,
        risk_level=RiskLevel.LOW,
        risk_factors=["Long-standing customer (5 years)", "Regular spending patterns"],
        typical_transaction_range_min=10.0,
        typical_transaction_range_max=200.0,
        usual_merchants=["Tesco", "Amazon", "Netflix", "Costa Coffee", "Shell"],
        usual_locations=["London", "Manchester", "Birmingham"],
        account_age_days=1825,
        previous_fraud_flags=0,
        last_updated="2025-01-15T10:00:00Z",
    )


# ---------------------------------------------------------------------------
# PatternMatcher tests
# ---------------------------------------------------------------------------

class TestPatternMatcher:
    def test_detect_anomalies_normal_transaction_returns_no_anomalies(
        self,
        normal_transaction: FlaggedTransaction,
        low_risk_profile: CustomerRiskProfile,
    ) -> None:
        """A normal, in-range transaction for a low-risk customer has no anomalies."""
        anomalies = PatternMatcher.detect_anomalies(normal_transaction, low_risk_profile)
        assert anomalies == [], f"Expected no anomalies, got: {anomalies}"

    def test_detect_anomalies_high_amount_triggers_amount_flag(
        self,
        high_amount_transaction: FlaggedTransaction,
        low_risk_profile: CustomerRiskProfile,
    ) -> None:
        """An amount 2x+ above the typical max must produce the amount anomaly."""
        anomalies = PatternMatcher.detect_anomalies(
            high_amount_transaction, low_risk_profile
        )
        assert any("Amount 2x+" in a for a in anomalies), (
            f"Expected an 'Amount 2x+' anomaly. Got: {anomalies}"
        )

    def test_detect_anomalies_high_risk_merchant_triggers_flag(
        self,
        low_risk_profile: CustomerRiskProfile,
    ) -> None:
        """A crypto-exchange transaction must produce a high-risk-merchant anomaly."""
        txn = FlaggedTransaction(
            transaction_id="TXN-TEST-003",
            customer_id="CUST-001",
            amount=100.0,
            currency="GBP",
            merchant_name="CoinBase",
            merchant_category="Crypto",
            location_country="GB",
            location_city="London",
            timestamp="2025-01-22T12:00:00Z",
            flag_reason="Crypto purchase",
            flag_score=0.55,
        )
        anomalies = PatternMatcher.detect_anomalies(txn, low_risk_profile)
        assert any("High-risk merchant" in a for a in anomalies), (
            f"Expected a high-risk merchant anomaly. Got: {anomalies}"
        )

    def test_calculate_composite_risk_score_returns_valid_float(
        self,
        normal_transaction: FlaggedTransaction,
        low_risk_profile: CustomerRiskProfile,
    ) -> None:
        """Composite score must be a float in [0, 1]."""
        anomalies = PatternMatcher.detect_anomalies(normal_transaction, low_risk_profile)
        score, level = PatternMatcher.calculate_composite_risk_score(
            normal_transaction, low_risk_profile, anomalies
        )
        assert isinstance(score, float), "Score should be a float"
        assert 0.0 <= score <= 1.0, f"Score {score} is outside [0, 1]"
        assert level in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

    def test_calculate_composite_risk_score_high_risk(
        self,
        high_amount_transaction: FlaggedTransaction,
        low_risk_profile: CustomerRiskProfile,
    ) -> None:
        """A high flag_score transaction should produce a higher composite score than a low one."""
        anomalies_high = PatternMatcher.detect_anomalies(
            high_amount_transaction, low_risk_profile
        )
        score_high, _ = PatternMatcher.calculate_composite_risk_score(
            high_amount_transaction, low_risk_profile, anomalies_high
        )

        low_txn = FlaggedTransaction(
            transaction_id="TXN-LOW",
            customer_id="CUST-001",
            amount=50.0,
            currency="GBP",
            merchant_name="Tesco",
            merchant_category="Grocery",
            location_country="GB",
            location_city="London",
            timestamp="2025-01-22T12:00:00Z",
            flag_reason="Velocity check",
            flag_score=0.20,
        )
        anomalies_low = PatternMatcher.detect_anomalies(low_txn, low_risk_profile)
        score_low, _ = PatternMatcher.calculate_composite_risk_score(
            low_txn, low_risk_profile, anomalies_low
        )

        assert score_high > score_low, (
            f"High-risk score ({score_high}) should exceed low-risk score ({score_low})"
        )

    def test_compute_pattern_hash_is_deterministic(
        self,
        normal_transaction: FlaggedTransaction,
    ) -> None:
        """The same transaction must always produce the same pattern hash."""
        hash1 = PatternMatcher.compute_pattern_hash(normal_transaction)
        hash2 = PatternMatcher.compute_pattern_hash(normal_transaction)
        assert hash1 == hash2
        assert len(hash1) == 32  # MD5 hex digest length


# ---------------------------------------------------------------------------
# RiskProfileCache tests
# ---------------------------------------------------------------------------

class TestRiskProfileCache:
    @pytest.mark.asyncio
    async def test_get_profile_known_customer_returns_correct_risk_score(self) -> None:
        """Fetching a known customer profile must return the expected risk score."""
        cache = RiskProfileCache()
        profile = await cache.get_profile("CUST-001")
        assert profile.customer_id == "CUST-001"
        assert profile.risk_score == 15
        assert profile.risk_level == RiskLevel.LOW

    @pytest.mark.asyncio
    async def test_get_profile_known_high_risk_customer(self) -> None:
        """CUST-002 is a HIGH-risk customer with previous fraud flags."""
        cache = RiskProfileCache()
        profile = await cache.get_profile("CUST-002")
        assert profile.customer_id == "CUST-002"
        assert profile.risk_score == 72
        assert profile.risk_level == RiskLevel.HIGH
        assert profile.previous_fraud_flags == 3

    @pytest.mark.asyncio
    async def test_get_profile_unknown_customer_returns_default_medium_risk(
        self,
    ) -> None:
        """An unknown customer should fall back to a medium-risk default profile."""
        cache = RiskProfileCache()
        profile = await cache.get_profile("CUST-UNKNOWN-9999")
        assert profile.customer_id == "CUST-UNKNOWN-9999"
        assert profile.risk_score == 45
        assert profile.risk_level == RiskLevel.MEDIUM

    @pytest.mark.asyncio
    async def test_get_similar_cases_returns_patterns(self) -> None:
        """get_similar_cases must return a non-empty list of FraudPattern objects."""
        from src.models import FraudPattern

        cache = RiskProfileCache()
        patterns = await cache.get_similar_cases(
            transaction_amount=2450.0,
            flag_reason="International transaction in high-risk country, 12x above typical amount",
        )
        assert len(patterns) > 0
        assert all(isinstance(p, FraudPattern) for p in patterns)

    @pytest.mark.asyncio
    async def test_get_similar_cases_respects_limit(self) -> None:
        """get_similar_cases must not return more patterns than the limit."""
        cache = RiskProfileCache()
        patterns = await cache.get_similar_cases(
            transaction_amount=100.0,
            flag_reason="Generic flag",
            limit=2,
        )
        assert len(patterns) <= 2


# ---------------------------------------------------------------------------
# EventHubProcessor tests
# ---------------------------------------------------------------------------

class TestEventHubProcessor:
    @pytest.mark.asyncio
    async def test_generate_simulated_transaction_high_risk(self) -> None:
        """Simulate 'high_risk' must return the Lagos electronics transaction."""
        processor = EventHubProcessor()
        txn = await processor.generate_simulated_transaction("high_risk")
        assert txn.transaction_id == "TXN-20250122-001"
        assert txn.customer_id == "CUST-001"
        assert txn.location_country == "NG"
        assert txn.flag_score == 0.94

    @pytest.mark.asyncio
    async def test_generate_simulated_transaction_low_risk(self) -> None:
        """Simulate 'low_risk' must return the Tesco Express transaction."""
        processor = EventHubProcessor()
        txn = await processor.generate_simulated_transaction("low_risk")
        assert txn.transaction_id == "TXN-20250122-002"
        assert txn.merchant_name == "Tesco Express"
        assert txn.flag_score == 0.42

    @pytest.mark.asyncio
    async def test_generate_simulated_transaction_velocity(self) -> None:
        """Simulate 'velocity' must return the crypto velocity transaction."""
        processor = EventHubProcessor()
        txn = await processor.generate_simulated_transaction("velocity")
        assert txn.transaction_id == "TXN-20250122-003"
        assert txn.merchant_category == "Cryptocurrency"

    @pytest.mark.asyncio
    async def test_generate_simulated_transaction_unknown_defaults_to_high_risk(
        self,
    ) -> None:
        """An unknown scenario name should default to the high_risk sample."""
        processor = EventHubProcessor()
        txn = await processor.generate_simulated_transaction("nonexistent_scenario")
        assert txn.transaction_id == "TXN-20250122-001"

    def test_mock_mode_is_true_by_default(self) -> None:
        """EventHubProcessor must start in mock mode when MOCK_MODE=true."""
        processor = EventHubProcessor()
        assert processor.mock_mode is True
