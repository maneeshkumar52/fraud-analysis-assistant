import asyncio, sys
sys.path.insert(0, '.')

async def main():
    print("=== Fraud Analysis Assistant - End-to-End Demo ===\n")

    # Test 1: Risk Profile Cache (mock mode, no Redis needed)
    from src.risk_profile import RiskProfileCache
    cache = RiskProfileCache()

    print("--- Customer Risk Profiles ---")
    for cust_id in ["CUST-001", "CUST-002", "CUST-003"]:
        profile = await cache.get_profile(cust_id)
        print(f"{cust_id}: Risk Score {profile.risk_score}/100 ({profile.risk_level.value})")
        print(f"  Factors: {profile.risk_factors[:2]}")
        print(f"  Usual locations: {profile.usual_locations}")
        print(f"  Transaction range: {profile.typical_transaction_range_min}-{profile.typical_transaction_range_max}")
        print()

    # Test unknown customer
    unknown = await cache.get_profile("CUST-UNKNOWN")
    print(f"Unknown customer default: Risk Score {unknown.risk_score} ({unknown.risk_level.value})")

    # Test 2: Pattern Matcher
    from src.pattern_matcher import PatternMatcher
    from src.models import FlaggedTransaction, CustomerRiskProfile, RiskLevel

    matcher = PatternMatcher()

    # High risk transaction
    txn_high = FlaggedTransaction(
        transaction_id="TXN-DEMO-001",
        customer_id="CUST-001",
        amount=2450.00,
        currency="GBP",
        merchant_name="ElectroMart Lagos",
        merchant_category="Electronics",
        location_country="NG",
        location_city="Lagos",
        timestamp="2025-01-22T03:17:42Z",
        flag_reason="International transaction in high-risk country, 12x above typical amount",
        flag_score=0.94
    )

    profile_low_risk = await cache.get_profile("CUST-001")
    anomalies = matcher.detect_anomalies(txn_high, profile_low_risk)
    risk_score, risk_level = matcher.calculate_composite_risk_score(txn_high, profile_low_risk, anomalies)

    print(f"\n--- High Risk Transaction Analysis ---")
    print(f"Transaction: {txn_high.amount} at {txn_high.merchant_name}, {txn_high.location_city}")
    print(f"Anomalies detected ({len(anomalies)}):")
    for a in anomalies:
        print(f"  [!] {a}")
    print(f"Composite Risk Score: {risk_score:.2f} ({risk_level})")

    # Low risk transaction
    txn_low = FlaggedTransaction(
        transaction_id="TXN-DEMO-002",
        customer_id="CUST-001",
        amount=89.50,
        currency="GBP",
        merchant_name="Tesco Express",
        merchant_category="Grocery",
        location_country="GB",
        location_city="London",
        timestamp="2025-01-22T14:32:11Z",
        flag_reason="Velocity flag - 3rd transaction today",
        flag_score=0.42
    )

    anomalies_low = matcher.detect_anomalies(txn_low, profile_low_risk)
    risk_score_low, risk_level_low = matcher.calculate_composite_risk_score(txn_low, profile_low_risk, anomalies_low)
    print(f"\n--- Low Risk Transaction Analysis ---")
    print(f"Transaction: {txn_low.amount} at {txn_low.merchant_name}, {txn_low.location_city}")
    print(f"Anomalies detected: {len(anomalies_low)}")
    print(f"Composite Risk Score: {risk_score_low:.2f} ({risk_level_low})")

    # Test 3: Streaming analysis fallback (when OpenAI unavailable)
    from src.analyser import FraudAnalyser
    analyser = FraudAnalyser()

    print(f"\n--- Streaming Analysis (Fallback Mode) ---")
    similar_patterns = await cache.get_similar_cases(txn_high.amount, txn_high.flag_reason)

    analysis_text = ""
    async for chunk in analyser.analyse_transaction(txn_high, profile_low_risk, similar_patterns, anomalies):
        analysis_text += chunk

    print(f"Streaming analysis generated ({len(analysis_text)} chars)")
    print(f"  Preview: {analysis_text[:200]}...")

    # Test 4: Event processor
    from src.event_processor import EventHubProcessor
    processor = EventHubProcessor()

    for scenario in ["high_risk", "low_risk", "velocity"]:
        txn = await processor.generate_simulated_transaction(scenario)
        print(f"\nSimulated {scenario} transaction:")
        print(f"  {txn.transaction_id}: {txn.amount} at {txn.merchant_name}")
        print(f"  Flag score: {txn.flag_score}, Reason: {txn.flag_reason[:50]}...")

    print("\n=== Fraud Analysis Assistant: Pattern detection, risk profiling, streaming ready ===")

asyncio.run(main())
