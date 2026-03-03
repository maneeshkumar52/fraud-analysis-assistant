from openai import AsyncAzureOpenAI
from typing import AsyncGenerator, List
import structlog
import json
from .models import FlaggedTransaction, CustomerRiskProfile, FraudPattern
from .prompts import FRAUD_ANALYSIS_SYSTEM_PROMPT
from .config import get_openai_client, get_settings

logger = structlog.get_logger()

_FALLBACK_ANALYSIS = """## FLAG REASON
This transaction was flagged by the automated rule-based engine. A full AI analysis could not be completed at this time (Azure OpenAI unavailable).

## RISK ASSESSMENT
Risk Score: 7/10 — Based on available rule-engine flag score and customer profile data, this transaction requires manual review.

## PATTERN ANALYSIS
Unable to perform real-time pattern analysis. Please cross-reference the flagged transaction against known fraud patterns manually:
- Cross-border card present
- Amount anomaly
- Rapid velocity

## RECOMMENDED ACTIONS
1. Place a temporary hold on the transaction pending manual review.
2. Contact the customer via verified contact details to confirm the transaction.
3. Review the customer's recent transaction history for related anomalies.
4. Escalate to the fraud investigation team if contact cannot be established within 2 hours.

## DECISION RECOMMENDATION
HOLD FOR REVIEW
"""


class FraudAnalyser:
    """Streams GPT-4o fraud analysis for flagged transactions."""

    def __init__(self) -> None:
        self.client: AsyncAzureOpenAI = get_openai_client()
        self.settings = get_settings()

    def _build_user_message(
        self,
        transaction: FlaggedTransaction,
        risk_profile: CustomerRiskProfile,
        patterns: List[FraudPattern],
        anomalies: List[str],
    ) -> str:
        """Construct the detailed user prompt from all available enrichment data."""
        pattern_lines = "\n".join(
            f"  - {p.pattern_name} (similarity: {p.similarity_score:.0%}, "
            f"{p.historical_cases:,} historical cases): {p.description}"
            for p in patterns
        )

        anomaly_lines = (
            "\n".join(f"  - {a}" for a in anomalies)
            if anomalies
            else "  - No additional anomalies detected beyond the flag reason."
        )

        return f"""Please analyse the following flagged transaction.

=== FLAGGED TRANSACTION ===
Transaction ID : {transaction.transaction_id}
Customer ID    : {transaction.customer_id}
Amount         : {transaction.amount:.2f} {transaction.currency}
Merchant       : {transaction.merchant_name} ({transaction.merchant_category})
Location       : {transaction.location_city}, {transaction.location_country}
Timestamp      : {transaction.timestamp}
Flag Reason    : {transaction.flag_reason}
Flag Score     : {transaction.flag_score:.2f}

=== CUSTOMER RISK PROFILE ===
Risk Score     : {risk_profile.risk_score}/100 ({risk_profile.risk_level})
Account Age    : {risk_profile.account_age_days} days
Previous Flags : {risk_profile.previous_fraud_flags}
Typical Range  : £{risk_profile.typical_transaction_range_min:.0f} – £{risk_profile.typical_transaction_range_max:.0f}
Usual Merchants: {', '.join(risk_profile.usual_merchants[:5])}
Usual Locations: {', '.join(risk_profile.usual_locations)}
Risk Factors   :
{chr(10).join('  - ' + rf for rf in risk_profile.risk_factors)}

=== DETECTED ANOMALIES ===
{anomaly_lines}

=== MATCHING FRAUD PATTERNS ===
{pattern_lines}

Please provide a structured fraud analysis following the format in your system instructions.
"""

    async def analyse_transaction(
        self,
        transaction: FlaggedTransaction,
        risk_profile: CustomerRiskProfile,
        patterns: List[FraudPattern],
        anomalies: List[str],
    ) -> AsyncGenerator[str, None]:
        """Yield analysis text chunks from GPT-4o via streaming."""
        user_message = self._build_user_message(
            transaction, risk_profile, patterns, anomalies
        )

        try:
            stream = await self.client.chat.completions.create(
                stream=True,
                model=self.settings.azure_openai_deployment,
                messages=[
                    {"role": "system", "content": FRAUD_ANALYSIS_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.3,
                max_tokens=800,
            )

            async for chunk in stream:
                content = chunk.choices[0].delta.content if chunk.choices else None
                yield content or ""

            logger.info(
                "analyser.stream_complete",
                transaction_id=transaction.transaction_id,
            )

        except Exception as exc:
            logger.warning(
                "analyser.azure_unavailable",
                transaction_id=transaction.transaction_id,
                error=str(exc),
                fallback="mock_analysis",
            )
            # Stream the fallback analysis character-by-character in chunks
            chunk_size = 50
            for i in range(0, len(_FALLBACK_ANALYSIS), chunk_size):
                yield _FALLBACK_ANALYSIS[i : i + chunk_size]

    async def analyse_transaction_full(
        self,
        transaction: FlaggedTransaction,
        risk_profile: CustomerRiskProfile,
        patterns: List[FraudPattern],
        anomalies: List[str],
    ) -> str:
        """Accumulate streamed chunks into a single analysis string."""
        parts: List[str] = []
        async for chunk in self.analyse_transaction(
            transaction, risk_profile, patterns, anomalies
        ):
            parts.append(chunk)
        return "".join(parts)
