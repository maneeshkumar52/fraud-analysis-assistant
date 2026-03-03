import redis.asyncio as aioredis
import json
import structlog
from typing import Optional, List
from .models import CustomerRiskProfile, RiskLevel, FraudPattern

logger = structlog.get_logger()

# Mock customer risk profiles for local development
MOCK_PROFILES = {
    "CUST-001": {
        "customer_id": "CUST-001",
        "risk_score": 15,
        "risk_level": "LOW",
        "risk_factors": ["Long-standing customer (5 years)", "Regular spending patterns"],
        "typical_transaction_range_min": 10.0,
        "typical_transaction_range_max": 200.0,
        "usual_merchants": ["Tesco", "Amazon", "Netflix", "Costa Coffee", "Shell"],
        "usual_locations": ["London", "Manchester", "Birmingham"],
        "account_age_days": 1825,
        "previous_fraud_flags": 0,
        "last_updated": "2025-01-15T10:00:00Z",
    },
    "CUST-002": {
        "customer_id": "CUST-002",
        "risk_score": 72,
        "risk_level": "HIGH",
        "risk_factors": [
            "3 fraud flags in last 6 months",
            "Unusual international transactions",
            "Multiple card declines",
        ],
        "typical_transaction_range_min": 5.0,
        "typical_transaction_range_max": 500.0,
        "usual_merchants": [
            "Various online retailers",
            "Crypto exchanges",
            "Money transfer services",
        ],
        "usual_locations": ["London", "Paris", "Amsterdam", "Bucharest"],
        "account_age_days": 487,
        "previous_fraud_flags": 3,
        "last_updated": "2025-01-20T14:30:00Z",
    },
    "CUST-003": {
        "customer_id": "CUST-003",
        "risk_score": 50,
        "risk_level": "MEDIUM",
        "risk_factors": [
            "New account (< 1 year)",
            "Limited transaction history",
            "Recent address change",
        ],
        "typical_transaction_range_min": 20.0,
        "typical_transaction_range_max": 350.0,
        "usual_merchants": ["Sainsbury's", "ASOS", "Deliveroo", "Spotify"],
        "usual_locations": ["Leeds", "Sheffield"],
        "account_age_days": 180,
        "previous_fraud_flags": 0,
        "last_updated": "2025-01-18T09:00:00Z",
    },
    "CUST-004": {
        "customer_id": "CUST-004",
        "risk_score": 28,
        "risk_level": "LOW",
        "risk_factors": ["Business account", "Regular payroll-sized transactions"],
        "typical_transaction_range_min": 50.0,
        "typical_transaction_range_max": 5000.0,
        "usual_merchants": [
            "Various UK businesses",
            "Office supplies",
            "Software subscriptions",
        ],
        "usual_locations": ["London", "Edinburgh", "Bristol"],
        "account_age_days": 2190,
        "previous_fraud_flags": 1,
        "last_updated": "2025-01-10T11:00:00Z",
    },
    "CUST-005": {
        "customer_id": "CUST-005",
        "risk_score": 91,
        "risk_level": "CRITICAL",
        "risk_factors": [
            "Account under investigation",
            "5+ fraud flags",
            "Linked to known fraud network",
        ],
        "typical_transaction_range_min": 0.0,
        "typical_transaction_range_max": 10000.0,
        "usual_merchants": [
            "Crypto exchanges",
            "Wire transfers",
            "Electronics stores",
        ],
        "usual_locations": ["Multiple countries"],
        "account_age_days": 90,
        "previous_fraud_flags": 7,
        "last_updated": "2025-01-22T16:00:00Z",
    },
}

MOCK_FRAUD_PATTERNS = [
    {
        "pattern_id": "PAT-001",
        "pattern_name": "Cross-border card present",
        "description": "Card used in foreign country significantly different from home country",
        "similarity_score": 0.92,
        "historical_cases": 1247,
    },
    {
        "pattern_id": "PAT-002",
        "pattern_name": "Amount anomaly",
        "description": "Transaction amount significantly exceeds customer's typical range",
        "similarity_score": 0.87,
        "historical_cases": 3821,
    },
    {
        "pattern_id": "PAT-003",
        "pattern_name": "Rapid velocity",
        "description": "Multiple transactions in short time across different locations",
        "similarity_score": 0.95,
        "historical_cases": 892,
    },
    {
        "pattern_id": "PAT-004",
        "pattern_name": "High-risk merchant category",
        "description": "Transaction at merchant type commonly associated with fraud",
        "similarity_score": 0.78,
        "historical_cases": 567,
    },
    {
        "pattern_id": "PAT-005",
        "pattern_name": "Night-time anomaly",
        "description": "Unusual transaction at 2-5am local time for customer",
        "similarity_score": 0.65,
        "historical_cases": 2103,
    },
]

_DEFAULT_PROFILE = {
    "customer_id": "UNKNOWN",
    "risk_score": 45,
    "risk_level": "MEDIUM",
    "risk_factors": ["No profile found — defaulting to medium risk"],
    "typical_transaction_range_min": 0.0,
    "typical_transaction_range_max": 1000.0,
    "usual_merchants": [],
    "usual_locations": [],
    "account_age_days": 0,
    "previous_fraud_flags": 0,
    "last_updated": "2025-01-01T00:00:00Z",
}


class RiskProfileCache:
    """Retrieves customer risk profiles from Redis with mock fallback."""

    def __init__(self) -> None:
        self._redis: Optional[aioredis.Redis] = None
        self._use_mock: bool = False

    async def _get_redis(self) -> Optional[aioredis.Redis]:
        """Lazily initialise Redis connection, falling back to mock on failure."""
        if self._redis is not None:
            return self._redis
        if self._use_mock:
            return None
        try:
            from .config import get_settings

            settings = get_settings()
            client = aioredis.from_url(settings.redis_url, decode_responses=True)
            # Ping to confirm connectivity
            await client.ping()
            self._redis = client
            logger.info("redis.connected", url=settings.redis_url)
            return self._redis
        except Exception as exc:
            logger.warning("redis.unavailable", error=str(exc), fallback="mock_data")
            self._use_mock = True
            return None

    async def get_profile(self, customer_id: str) -> CustomerRiskProfile:
        """Return the risk profile for *customer_id*, falling back to mock data."""
        redis_client = await self._get_redis()
        if redis_client is not None:
            try:
                raw = await redis_client.get(f"risk_profile:{customer_id}")
                if raw:
                    data = json.loads(raw)
                    logger.info("profile.cache_hit", customer_id=customer_id)
                    return CustomerRiskProfile(**data)
            except Exception as exc:
                logger.warning(
                    "profile.redis_read_error",
                    customer_id=customer_id,
                    error=str(exc),
                )

        # Fall back to in-memory mock
        mock_data = MOCK_PROFILES.get(customer_id)
        if mock_data:
            logger.info("profile.mock_hit", customer_id=customer_id)
            return CustomerRiskProfile(**mock_data)

        # Unknown customer — return a sensible default
        logger.info("profile.default", customer_id=customer_id)
        default = dict(_DEFAULT_PROFILE)
        default["customer_id"] = customer_id
        return CustomerRiskProfile(**default)

    async def get_similar_cases(
        self,
        transaction_amount: float,
        flag_reason: str,
        limit: int = 5,
    ) -> List[FraudPattern]:
        """Return fraud patterns that match keywords found in the flag reason."""
        flag_lower = flag_reason.lower()
        keyword_map: dict[str, list[str]] = {
            "PAT-001": ["international", "foreign", "country", "cross-border", "border"],
            "PAT-002": ["amount", "typical", "range", "above", "large", "high"],
            "PAT-003": ["velocity", "rapid", "multiple", "minutes", "fast"],
            "PAT-004": ["crypto", "wire", "money transfer", "gambling", "casino"],
            "PAT-005": ["night", "overnight", "2am", "3am", "4am", "5am", "midnight"],
        }

        matched: List[FraudPattern] = []
        for pattern in MOCK_FRAUD_PATTERNS:
            keywords = keyword_map.get(pattern["pattern_id"], [])
            if any(kw in flag_lower for kw in keywords):
                matched.append(FraudPattern(**pattern))

        # If nothing matched, return the top-scoring patterns as a fallback
        if not matched:
            matched = [
                FraudPattern(**p)
                for p in sorted(
                    MOCK_FRAUD_PATTERNS, key=lambda x: x["similarity_score"], reverse=True
                )
            ]

        return matched[:limit]

    async def populate_redis(self) -> None:
        """Pre-populate Redis with all mock profiles on startup."""
        redis_client = await self._get_redis()
        if redis_client is None:
            logger.info("populate_redis.skipped", reason="mock_mode_or_unavailable")
            return
        try:
            for customer_id, profile_data in MOCK_PROFILES.items():
                await redis_client.set(
                    f"risk_profile:{customer_id}",
                    json.dumps(profile_data),
                    ex=86400,  # 24-hour TTL
                )
            logger.info(
                "populate_redis.done", profiles_loaded=len(MOCK_PROFILES)
            )
        except Exception as exc:
            logger.warning("populate_redis.error", error=str(exc))
