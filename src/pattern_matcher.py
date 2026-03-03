import hashlib
import structlog
from typing import List, Tuple
from .models import FlaggedTransaction, CustomerRiskProfile

logger = structlog.get_logger()

KNOWN_HIGH_RISK_COUNTRIES = ["NG", "GH", "RU", "UA", "VN", "KH"]  # ISO codes
HIGH_RISK_MERCHANTS = ["casino", "crypto", "wire transfer", "money order", "pawnshop"]


class PatternMatcher:
    """Detects transaction anomalies and computes composite risk scores."""

    @staticmethod
    def compute_pattern_hash(transaction: FlaggedTransaction) -> str:
        """Return an MD5 hash based on amount bucket, country, and merchant category."""
        # Bucket the amount into orders of magnitude to group similar transactions
        amount_bucket = f"{int(transaction.amount / 100) * 100}"
        raw = f"{amount_bucket}|{transaction.location_country}|{transaction.merchant_category.lower()}"
        return hashlib.md5(raw.encode()).hexdigest()

    @staticmethod
    def detect_anomalies(
        transaction: FlaggedTransaction,
        risk_profile: CustomerRiskProfile,
    ) -> List[str]:
        """Return a list of human-readable anomaly descriptions for the transaction."""
        anomalies: List[str] = []

        # Amount significantly above typical range
        if transaction.amount > risk_profile.typical_transaction_range_max * 2:
            anomalies.append(
                f"Amount 2x+ above typical range "
                f"(transaction: {transaction.amount:.2f}, "
                f"typical max: {risk_profile.typical_transaction_range_max:.2f})"
            )

        # Transaction in an unusual location (only flag for lower-risk customers where
        # the deviation is more meaningful)
        if (
            transaction.location_country not in risk_profile.usual_locations
            and transaction.location_city not in risk_profile.usual_locations
            and risk_profile.risk_score < 60
        ):
            anomalies.append(
                f"Transaction in unusual country/city: "
                f"{transaction.location_city}, {transaction.location_country}"
            )

        # High-risk merchant category
        merchant_lower = transaction.merchant_category.lower()
        if any(hrm in merchant_lower for hrm in HIGH_RISK_MERCHANTS):
            anomalies.append(
                f"High-risk merchant category: {transaction.merchant_category}"
            )

        # Previous fraud history
        if risk_profile.previous_fraud_flags > 0:
            anomalies.append(
                f"Customer has {risk_profile.previous_fraud_flags} previous fraud flag(s)"
            )

        return anomalies

    @staticmethod
    def calculate_composite_risk_score(
        transaction: FlaggedTransaction,
        risk_profile: CustomerRiskProfile,
        anomalies: List[str],
    ) -> Tuple[float, str]:
        """Compute a composite 0-1 risk score and corresponding risk-level label.

        The score is a weighted combination of:
          * The flag score from the rule engine          (40 %)
          * The customer's historical risk score         (30 %)
          * Anomaly count contribution                   (30 %)
        """
        flag_component = transaction.flag_score * 0.40
        profile_component = (risk_profile.risk_score / 100.0) * 0.30
        anomaly_component = min(len(anomalies) / 5.0, 1.0) * 0.30

        composite = flag_component + profile_component + anomaly_component
        composite = round(min(max(composite, 0.0), 1.0), 4)

        if composite >= 0.75:
            level = "CRITICAL"
        elif composite >= 0.50:
            level = "HIGH"
        elif composite >= 0.25:
            level = "MEDIUM"
        else:
            level = "LOW"

        logger.info(
            "pattern_matcher.composite_score",
            transaction_id=transaction.transaction_id,
            composite=composite,
            level=level,
            anomaly_count=len(anomalies),
        )
        return composite, level
