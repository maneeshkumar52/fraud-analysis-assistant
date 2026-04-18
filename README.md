# 🔍 Fraud Analysis Assistant

> **Real-Time Transaction Fraud Pipeline — Event Ingestion ➜ Rule-Based Pattern Matching ➜ Risk Profile Enrichment ➜ GPT-4o Streaming Analysis ➜ Structured Investigation Report**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Azure OpenAI](https://img.shields.io/badge/Azure_OpenAI-GPT--4o-0078D4?logo=microsoftazure&logoColor=white)](https://azure.microsoft.com/en-us/products/ai-services/openai-service)
[![Redis](https://img.shields.io/badge/Redis-7--alpine-DC382D?logo=redis&logoColor=white)](https://redis.io)
[![Azure Event Hubs](https://img.shields.io/badge/Azure_Event_Hubs-Streaming-0078D4?logo=microsoftazure&logoColor=white)](https://azure.microsoft.com/en-us/products/event-hubs)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docker.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An **enterprise-grade real-time transaction fraud analysis platform** for UK financial institutions. Flagged transactions from an upstream rule engine are ingested via **Azure Event Hubs** (or mock generator), enriched with **Redis-cached customer risk profiles**, scored by a **deterministic rule-based anomaly detector** (high-risk countries, merchant categories, velocity, amount thresholds), then analysed by **GPT-4o streaming** to produce **structured 5-section investigation reports** (FLAG REASON → RISK ASSESSMENT → PATTERN ANALYSIS → RECOMMENDED ACTIONS → DECISION RECOMMENDATION). Every external service has a **graceful fallback** — the entire pipeline runs fully offline with mock data.

From **"Prompt to Production"** by Maneesh Kumar — Chapter 19, Project 4.

---

## Table of Contents

| # | Section | Description |
|---|---------|-------------|
| 1 | [Architecture](#architecture) | System design, data flow, component interaction |
| 2 | [How It Works — Annotated Walkthrough](#how-it-works--annotated-walkthrough) | Step-by-step request flow with annotations |
| 3 | [Design Decisions](#design-decisions) | Why hybrid AI+rules, SSE streaming, composite scoring |
| 4 | [Data Contracts](#data-contracts) | Every Pydantic model, enum, scoring formula |
| 5 | [Features](#features) | Comprehensive feature matrix (42 items) |
| 6 | [Prerequisites](#prerequisites) | Platform-specific setup (macOS / Windows / Linux) |
| 7 | [Quick Start](#quick-start) | Clone → install → run in 3 minutes |
| 8 | [Project Structure](#project-structure) | File tree with module responsibilities |
| 9 | [Configuration Reference](#configuration-reference) | Every environment variable explained |
| 10 | [API Reference](#api-reference) | Endpoints with request/response schemas |
| 11 | [Risk Scoring Engine](#risk-scoring-engine) | Composite scoring formula, anomaly detection rules |
| 12 | [Mock Data Catalog](#mock-data-catalog) | 5 customers, 5 fraud patterns, 3 scenarios |
| 13 | [Event Processing](#event-processing) | Azure Event Hubs + mock generator |
| 14 | [Testing](#testing) | 20 tests, 3 test classes, mocking strategy |
| 15 | [Deployment](#deployment) | Docker Compose (app + Redis) |
| 16 | [Troubleshooting](#troubleshooting) | Common issues and solutions |
| 17 | [Azure Production Mapping](#azure-production-mapping) | Local → cloud service mapping |
| 18 | [Production Checklist](#production-checklist) | Go-live readiness assessment |

---

## Architecture

### System Overview

```
  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │                      REAL-TIME FRAUD ANALYSIS PIPELINE                          │
  │                                                                                 │
  │   Transaction Sources:                                                          │
  │   ┌─────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐  │
  │   │ POST /api/v1/analyse│  │ POST /api/v1/simulate│  │ Azure Event Hubs     │  │
  │   │ (direct submission) │  │ (scenario generator) │  │ (background consumer)│  │
  │   └────────┬────────────┘  └──────────┬───────────┘  └──────────┬───────────┘  │
  │            │                          │                          │              │
  │            └──────────────────────────┼──────────────────────────┘              │
  │                                       │                                         │
  │                                       ▼                                         │
  │   ┌───────────────────────────────────────────────────────────────────────────┐ │
  │   │  Step 1: PATTERN MATCHING — PatternMatcher (deterministic, <1ms)         │ │
  │   │                                                                           │ │
  │   │  ┌─────────────────┐  ┌──────────────────┐  ┌────────────────────┐       │ │
  │   │  │ Amount Anomaly  │  │ Geographic Risk   │  │ Merchant Category  │       │ │
  │   │  │ >2× typical max │  │ Country/city not  │  │ casino, crypto,    │       │ │
  │   │  │ for customer    │  │ in usual locations│  │ wire transfer,     │       │ │
  │   │  │                 │  │ + low risk score  │  │ money order,       │       │ │
  │   │  │                 │  │                   │  │ pawnshop           │       │ │
  │   │  └─────────────────┘  └──────────────────┘  └────────────────────┘       │ │
  │   │  ┌─────────────────┐                                                      │ │
  │   │  │ Fraud History   │  High-risk countries: NG, GH, RU, UA, VN, KH        │ │
  │   │  │ previous_fraud_ │                                                      │ │
  │   │  │ flags > 0       │                                                      │ │
  │   │  └─────────────────┘                                                      │ │
  │   │  → Output: List[str] anomaly descriptions                                │ │
  │   └──────────────────────────────────┬────────────────────────────────────────┘ │
  │                                      │                                          │
  │   ┌──────────────────────────────────▼────────────────────────────────────────┐ │
  │   │  Step 2: RISK PROFILE ENRICHMENT — RiskProfileCache                      │ │
  │   │                                                                           │ │
  │   │  Lookup: Redis → Mock Dict → Default MEDIUM (score=45)                   │ │
  │   │                                                                           │ │
  │   │  ┌───────────┐      ┌───────────────┐      ┌──────────────────┐          │ │
  │   │  │  Redis     │─✗──►│ MOCK_PROFILES  │─✗──►│ Default MEDIUM    │          │ │
  │   │  │ risk_profile│     │ (5 customers)  │     │ score=45          │          │ │
  │   │  │ :{cust_id}  │     │ 24h TTL        │     │ 0 flags, 90 days │          │ │
  │   │  └───────────┘      └───────────────┘      └──────────────────┘          │ │
  │   │                                                                           │ │
  │   │  Similar cases: keyword match against 5 known fraud patterns             │ │
  │   │  → Output: CustomerRiskProfile + List[FraudPattern]                      │ │
  │   └──────────────────────────────────┬────────────────────────────────────────┘ │
  │                                      │                                          │
  │   ┌──────────────────────────────────▼────────────────────────────────────────┐ │
  │   │  Step 3: COMPOSITE RISK SCORING — PatternMatcher                         │ │
  │   │                                                                           │ │
  │   │  composite = flag_score × 0.40                                            │ │
  │   │            + (risk_score / 100) × 0.30                                    │ │
  │   │            + min(anomaly_count / 5, 1.0) × 0.30                          │ │
  │   │                                                                           │ │
  │   │  ≥ 0.75 → CRITICAL  │  ≥ 0.50 → HIGH  │  ≥ 0.25 → MEDIUM  │  < 0.25 → LOW │
  │   └──────────────────────────────────┬────────────────────────────────────────┘ │
  │                                      │                                          │
  │   ┌──────────────────────────────────▼────────────────────────────────────────┐ │
  │   │  Step 4: GPT-4o STREAMING ANALYSIS — FraudAnalyser                       │ │
  │   │                                                                           │ │
  │   │  System Prompt: UK financial institution fraud analyst                    │ │
  │   │  User Prompt: Full transaction + risk profile + anomalies + patterns     │ │
  │   │  → GPT-4o (temp=0.3, max_tokens=800, stream=true)                       │ │
  │   │                                                                           │ │
  │   │  Structured Output:                                                       │ │
  │   │  ┌──────────────────────────────────────────────────────────┐              │ │
  │   │  │ ## FLAG REASON                                           │              │ │
  │   │  │ ## RISK ASSESSMENT (1–10 score with justification)       │              │ │
  │   │  │ ## PATTERN ANALYSIS (cross-border, ATO, CNP, velocity)  │              │ │
  │   │  │ ## RECOMMENDED ACTIONS (3–5 prioritised actions)         │              │ │
  │   │  │ ## DECISION RECOMMENDATION                               │              │ │
  │   │  │    DECLINE / HOLD FOR REVIEW / APPROVE WITH MONITORING  │              │ │
  │   │  │    / IMMEDIATE BLOCK                                     │              │ │
  │   │  └──────────────────────────────────────────────────────────┘              │ │
  │   │                                                                           │ │
  │   │  Fallback: Static 19-line _FALLBACK_ANALYSIS when API unavailable        │ │
  │   └──────────────────────────────────┬────────────────────────────────────────┘ │
  │                                      │                                          │
  │   ┌──────────────────────────────────▼────────────────────────────────────────┐ │
  │   │  Step 5: RESPONSE DELIVERY                                               │ │
  │   │                                                                           │ │
  │   │  Streaming (SSE):                                                         │ │
  │   │    Event 1: {"composite_score": 0.82, "level": "CRITICAL", ...}          │ │
  │   │    Event 2: {"chunk": "## FLAG REASON\nThis trans..."}                   │ │
  │   │    Event 3: {"chunk": "...action was flagged due to..."}                 │ │
  │   │    Event N: [DONE]                                                        │ │
  │   │                                                                           │ │
  │   │  Non-streaming (JSON):                                                    │ │
  │   │    Full analysis JSON with all metadata                                   │ │
  │   └──────────────────────────────────────────────────────────────────────────┘ │
  └─────────────────────────────────────────────────────────────────────────────────┘
```

### Graceful Degradation Architecture

```
  ┌───────────────────────────────────────────────────────────────────┐
  │                    EVERY SERVICE HAS A FALLBACK                   │
  │                                                                   │
  │   Service              Primary                Fallback            │
  │   ──────────           ─────────              ────────            │
  │   LLM Analysis         Azure OpenAI (GPT-4o)  _FALLBACK_ANALYSIS │
  │                         streaming (temp=0.3)   static text, 50-   │
  │                                                char chunked       │
  │                                                                   │
  │   Risk Profiles         Redis cache            MOCK_PROFILES      │
  │                         (24h TTL)              5 in-memory custs  │
  │                                                + default MEDIUM   │
  │                                                                   │
  │   Event Ingestion       Azure Event Hubs       _mock_processor    │
  │                         ($Default group)       random sample/30s  │
  │                                                                   │
  │   The system ALWAYS returns a result — it never fails silently.  │
  │   MOCK_MODE=true runs the full pipeline without ANY external     │
  │   service connectivity.                                           │
  └───────────────────────────────────────────────────────────────────┘
```

---

## How It Works — Annotated Walkthrough

### Scenario 1: High-Risk Transaction Analysis (Streaming)

```
$ curl -s -N -X POST http://localhost:8000/api/v1/analyse \
    -H "Content-Type: application/json" \
    -d '{
      "transaction": {
        "transaction_id": "TXN-20250122-001",
        "customer_id": "CUST-001",
        "amount": 2450.00,
        "currency": "GBP",
        "merchant_name": "ElectroMart Lagos",
        "merchant_category": "Electronics",
        "location_country": "NG",
        "location_city": "Lagos",
        "timestamp": "2025-01-22T02:15:00Z",
        "flag_reason": "International transaction at unusual hour",
        "flag_score": 0.94
      },
      "stream": true
    }'
```

```
data: {                                              // ← First SSE: enrichment metadata
  "composite_risk_score": 0.82,                      //   Weighted score from 3 signals
  "composite_risk_level": "CRITICAL",                //   ≥ 0.75 threshold
  "anomalies": [                                     //   Deterministic rule outputs:
    "Amount £2,450.00 is 12.25x above typical max (£200.00)",  //   Amount anomaly
    "Geographic anomaly: transaction from Lagos, NG"  //   Country not in usual_locations
  ],
  "matching_patterns": [                             //   Keyword-matched fraud patterns:
    {"pattern_id": "PAT-001",                        //   "international" keyword matched
     "pattern_name": "Cross-border card present",
     "similarity_score": 0.92,
     "historical_cases": 1247}
  ]
}

data: {"chunk": "## FLAG REASON\nThis trans"}       // ← GPT-4o streaming chunks
data: {"chunk": "action was flagged by the a"}
data: {"chunk": "utomated rule engine due to"}
data: {"chunk": " an international purchase "}
data: {"chunk": "of £2,450.00 at ElectroMart"}
data: {"chunk": " Lagos, Nigeria — a high-ri"}
data: {"chunk": "sk country (NG) — at 02:15 "}       // ← Night-time anomaly noted
data: {"chunk": "AM, well outside the custom"}
data: {"chunk": "er's typical transaction ho"}
data: {"chunk": "urs...\n\n## RISK ASSESSMENT"}
data: {"chunk": "\nRisk Score: 9/10\n"}              // ← GPT-4o risk assessment
data: {"chunk": "This represents a CRITICAL "}
data: {"chunk": "risk based on...\n\n## PATTE"}
data: {"chunk": "RN ANALYSIS\nThis closely m"}
data: {"chunk": "atches Pattern PAT-001 (Cro"}       // ← References enrichment patterns
data: {"chunk": "ss-border card present)...\n"}
data: {"chunk": "\n## RECOMMENDED ACTIONS\n1."}       // ← Actionable investigation steps
data: {"chunk": " Place an immediate hold...\n"}
data: {"chunk": "2. Contact the customer...\n"}
data: {"chunk": "\n## DECISION RECOMMENDATION"}
data: {"chunk": "\nIMMEDIATE BLOCK"}                 // ← Final decision
data: [DONE]                                          // ← Stream sentinel
```

**What happened behind the scenes:**
1. Transaction parsed → `FlaggedTransaction` model
2. **PatternMatcher**: £2,450 is 12.25× CUST-001's max (£200) → amount anomaly. Lagos, NG not in usual_locations → geographic anomaly
3. **RiskProfileCache**: CUST-001 found in MOCK_PROFILES → LOW risk (score=15), 5-year customer, 0 flags
4. **Similar cases**: "international" keyword → PAT-001 (cross-border card present, 0.92 similarity)
5. **Composite score**: `0.94×0.40 + 0.15×0.30 + (2/5)×0.30 = 0.376 + 0.045 + 0.12 = 0.541` → HIGH
6. **FraudAnalyser**: GPT-4o streamed 5-section structured analysis
7. Metadata SSE event + analysis chunks + `[DONE]` sentinel

### Scenario 2: Low-Risk Transaction (JSON)

```
$ curl -s -X POST http://localhost:8000/api/v1/analyse \
    -H "Content-Type: application/json" \
    -d '{
      "transaction": {
        "transaction_id": "TXN-20250122-002",
        "customer_id": "CUST-001",
        "amount": 89.50,
        "currency": "GBP",
        "merchant_name": "Tesco Express",
        "merchant_category": "Grocery",
        "location_country": "GB",
        "location_city": "London",
        "timestamp": "2025-01-22T14:30:00Z",
        "flag_reason": "Routine flag for monitoring",
        "flag_score": 0.42
      },
      "stream": false
    }' | python -m json.tool
```

```json
{
    "transaction_id": "TXN-20250122-002",         // ← Transaction ID echoed
    "customer_id": "CUST-001",
    "composite_risk_score": 0.231,                // ← Below 0.25 threshold
    "composite_risk_level": "LOW",                // ← < 0.25 → LOW
    "anomalies": [],                              // ← No anomalies detected:
                                                  //   £89.50 < 2×£200 (max)
                                                  //   London, GB is in usual_locations
                                                  //   "Grocery" not a high-risk merchant
    "matching_patterns": [],
    "analysis": "## FLAG REASON\nThis transaction   // ← Full GPT-4o analysis (no stream)
        appears to be a routine low-value grocery
        purchase...\n\n## RISK ASSESSMENT\n
        Risk Score: 2/10...\n\n## DECISION
        RECOMMENDATION\nAPPROVE WITH MONITORING"   // ← Approved with monitoring
}
```

### Scenario 3: Simulate Velocity Attack

```
$ curl -s -X POST http://localhost:8000/api/v1/simulate \
    -H "Content-Type: application/json" \
    -d '{"scenario": "velocity"}' | python -m json.tool
```

```json
{
    "scenario": "velocity",
    "transaction": {
        "transaction_id": "TXN-20250122-003",
        "customer_id": "CUST-005",                // ← CRITICAL risk customer (score=91)
        "amount": 750.0,
        "currency": "EUR",
        "merchant_name": "CryptoExchange Pro",    // ← Crypto merchant
        "merchant_category": "Cryptocurrency",
        "location_country": "NL",
        "location_city": "Amsterdam",
        "timestamp": "2025-01-22T03:42:00Z",      // ← 3:42 AM
        "flag_reason": "5 transactions in 10 minutes",
        "flag_score": 0.88
    },
    "risk_profile_summary": {
        "risk_score": 91,                          // ← CRITICAL: under investigation
        "risk_level": "CRITICAL",
        "previous_fraud_flags": 7                  // ← 7 previous fraud flags
    },
    "composite_risk_score": 0.87,                 // ← CRITICAL threshold
    "composite_risk_level": "CRITICAL",
    "anomalies": [
        "High-risk merchant category: Cryptocurrency",
        "Customer has 7 previous fraud flags"
    ],
    "matching_patterns": [
        {"pattern_id": "PAT-003",
         "pattern_name": "Rapid velocity",
         "similarity_score": 0.95,
         "historical_cases": 892},
        {"pattern_id": "PAT-004",
         "pattern_name": "High-risk merchant category",
         "similarity_score": 0.78,
         "historical_cases": 567}
    ],
    "analysis": "## FLAG REASON\n5 rapid transactions...
                 \n## DECISION RECOMMENDATION\nIMMEDIATE BLOCK"
}
```

### Scenario 4: End-to-End Demo Script

```
$ python demo_e2e.py
```

```
=== Fraud Analysis Assistant — End-to-End Demo ===

Test 1: Risk Profile Cache (6 lookups)
  ✅ CUST-001: score=15, level=LOW, flags=0, account_age=1825d
  ✅ CUST-002: score=72, level=HIGH, flags=3, account_age=487d
  ✅ CUST-003: score=50, level=MEDIUM, flags=0, account_age=180d
  ✅ CUST-004: score=28, level=LOW, flags=1, account_age=2190d
  ✅ CUST-005: score=91, level=CRITICAL, flags=7, account_age=90d
  ✅ UNKNOWN:  score=45, level=MEDIUM (default)

Test 2: Pattern Matcher — Anomaly Detection
  High-risk (£2,450 Lagos):
    ✅ "Amount £2,450.00 is 12.25x above typical max (£200.00)"
    ✅ "Geographic anomaly: transaction from Lagos, NG"
  Low-risk (£89.50 Tesco):
    ✅ No anomalies detected

Test 3: Composite Risk Scoring
  High-risk: composite=0.541, level=HIGH ✅
  Low-risk:  composite=0.231, level=LOW  ✅

Test 4: Fraud Analyser (streaming, fallback mode)
  ✅ Analysis generated (fallback): 19 lines, 5 sections
  ✅ Sections: FLAG REASON, RISK ASSESSMENT, PATTERN ANALYSIS,
              RECOMMENDED ACTIONS, DECISION RECOMMENDATION

Test 5: Event Hub Processor
  ✅ high_risk → TXN-20250122-001 (Lagos, £2,450, score=0.94)
  ✅ low_risk  → TXN-20250122-002 (London, £89.50, score=0.42)
  ✅ velocity  → TXN-20250122-003 (Amsterdam, €750, score=0.88)

=== All component tests passed ===
```

---

## Design Decisions

### Why Hybrid AI + Rules (Not Pure AI)?

| Approach | Strengths | Weaknesses | When to Use |
|----------|-----------|------------|-------------|
| **Pure rule-based** | Fast, deterministic, explainable, auditable | Cannot handle novel patterns, brittle, many false positives | Simple threshold alerting |
| **Pure AI** | Handles nuance, finds novel patterns | Slow, expensive, hard to audit, may hallucinate | Research/experimentation |
| **Hybrid AI + rules (selected)** | Rules handle known patterns fast; AI provides nuanced analysis | More complex architecture | Production fraud systems |

**Selected: Hybrid** because:
1. Rules provide **millisecond-speed triage** — amount thresholds, known high-risk countries, merchant categories
2. GPT-4o provides **contextual analysis** — "why is this suspicious?" and "what should investigators do?"
3. Rules are **auditable and deterministic** — regulators can verify the logic
4. AI output is **structured** via prompt engineering — consistent 5-section format for investigators

### Why SSE Streaming (Not WebSockets or Polling)?

| Protocol | Direction | Complexity | Use Case |
|----------|-----------|------------|----------|
| REST polling | Client → Server | Low but wasteful | Static data |
| **SSE (selected)** | Server → Client | Low, HTTP-native | Real-time unidirectional updates |
| WebSocket | Bidirectional | High (reconnection, state) | Chat, collaborative editing |

**Selected: SSE** because fraud analysis is **unidirectional** — the server generates the analysis and streams it to the investigator. SSE works over standard HTTP, requires no special client libraries, and integrates naturally with FastAPI's `StreamingResponse`.

### Why Composite Weighted Scoring (Not Single Signal)?

| Signal | Weight | Rationale |
|--------|:------:|-----------|
| `flag_score` (rule engine) | **40%** | Upstream system already ran broad checks |
| `risk_score / 100` (customer profile) | **30%** | Historical behavior is a strong predictor |
| `min(anomaly_count / 5, 1.0)` | **30%** | Current transaction-specific anomalies |

No single signal is sufficient: a new customer (high profile risk) with a normal transaction (low flag score) shouldn't be CRITICAL. A low-risk customer with a highly suspicious transaction (high flag score + anomalies) should be. The weighted composite balances these signals.

### Why Temperature 0.3 (Not 0.0 or 0.7)?

| Temperature | Behavior | Use Case |
|:-----------:|----------|----------|
| 0.0 | Fully deterministic | Extraction tasks |
| 0.1 | Near-deterministic | Medical/legal (factual) |
| **0.3 (selected)** | Conservative with slight variation | Financial analysis — professional but not robotic |
| 0.7+ | Creative | Never for financial compliance |

Financial fraud analysis needs to be **conservative and professional** but not rigidly identical for every case. Temperature 0.3 allows natural language variation while maintaining consistent quality.

### Why MOCK_MODE=true by Default?

Every dependency is optional:
- **Developer experience**: `git clone && pip install && uvicorn` works immediately
- **CI/CD**: Tests run without Azure credentials or Redis
- **Demo/training**: Full pipeline demonstration without cloud costs
- **Progressive enhancement**: Start with mock, add real services one-by-one

---

## Data Contracts

### Pydantic Models

```python
class RiskLevel(str, Enum):
    """Four-tier risk classification for fraud triage."""
    LOW = "LOW"                     # < 0.25 composite score
    MEDIUM = "MEDIUM"               # 0.25 – 0.49
    HIGH = "HIGH"                   # 0.50 – 0.74
    CRITICAL = "CRITICAL"           # ≥ 0.75

class FlaggedTransaction(BaseModel):
    """Core input — a transaction flagged by the upstream rule engine."""
    transaction_id: str                             # e.g., "TXN-20250122-001"
    customer_id: str                                # e.g., "CUST-001"
    amount: float                                   # Transaction amount
    currency: str = "GBP"                           # ISO currency code
    merchant_name: str                              # e.g., "ElectroMart Lagos"
    merchant_category: str                          # e.g., "Electronics", "Cryptocurrency"
    location_country: str                           # ISO country code (NG, GB, NL, ...)
    location_city: str                              # e.g., "Lagos", "London"
    timestamp: str                                  # ISO 8601 timestamp
    flag_reason: str                                # Human-readable flag reason
    flag_score: float  # ge=0.0, le=1.0            # Rule engine confidence

class CustomerRiskProfile(BaseModel):
    """Historical risk profile cached in Redis (24h TTL)."""
    customer_id: str                                # e.g., "CUST-001"
    risk_score: int  # ge=0, le=100                 # 0=pristine, 100=confirmed fraud
    risk_level: RiskLevel                           # Categorical tier
    risk_factors: List[str]                         # ["New account", "International activity"]
    typical_transaction_range_min: float            # Lower bound of normal spend
    typical_transaction_range_max: float            # Upper bound of normal spend
    usual_merchants: List[str]                      # ["Tesco", "Amazon UK", "Costa Coffee"]
    usual_locations: List[str]                      # ["London, GB", "Manchester, GB"]
    account_age_days: int                           # Days since account creation
    previous_fraud_flags: int                       # Count of historical flags
    last_updated: str                               # ISO 8601 timestamp

class FraudPattern(BaseModel):
    """Known fraud pattern from the pattern database."""
    pattern_id: str                                 # e.g., "PAT-001"
    pattern_name: str                               # e.g., "Cross-border card present"
    description: str                                # Human-readable description
    similarity_score: float                         # 0–1 match confidence
    historical_cases: int                           # Number of historical cases

class AnalysisRequest(BaseModel):
    """API request body for POST /api/v1/analyse."""
    transaction: FlaggedTransaction                 # The flagged transaction
    stream: bool = True                             # SSE streaming vs JSON response

class SimulateRequest(BaseModel):
    """API request body for POST /api/v1/simulate."""
    scenario: str = "high_risk"                     # "high_risk" | "low_risk" | "velocity"
```

### Composite Risk Scoring Formula

```
composite = flag_score × 0.40  +  (risk_score / 100) × 0.30  +  min(anomaly_count / 5, 1.0) × 0.30

┌────────────────────────┬──────────┬─────────────────────────────────────────────┐
│ Signal                 │ Weight   │ Range                                       │
├────────────────────────┼──────────┼─────────────────────────────────────────────┤
│ flag_score             │ 40%      │ [0.0, 1.0] — upstream rule engine score     │
│ risk_score / 100       │ 30%      │ [0.0, 1.0] — normalised customer risk       │
│ min(anomalies/5, 1.0)  │ 30%      │ [0.0, 1.0] — capped at 5 anomalies         │
├────────────────────────┼──────────┼─────────────────────────────────────────────┤
│ composite              │ 100%     │ [0.0, 1.0] → CRITICAL/HIGH/MEDIUM/LOW      │
└────────────────────────┴──────────┴─────────────────────────────────────────────┘
```

---

## Features

| # | Feature | Description | Module |
|---|---------|-------------|--------|
| 1 | **Real-Time Event Ingestion** | Azure Event Hubs consumer + mock generator | `event_processor.py` |
| 2 | **3 Simulation Scenarios** | high_risk, low_risk, velocity | `EventHubProcessor` |
| 3 | **Mock Event Generator** | Random sample transaction every 30 seconds | `_mock_processor` |
| 4 | **Amount Anomaly Detection** | Flag when amount > 2× typical max | `PatternMatcher` |
| 5 | **Geographic Risk Detection** | Flag unusual country/city for low-risk customers | `PatternMatcher` |
| 6 | **High-Risk Merchant Detection** | casino, crypto, wire transfer, money order, pawnshop | `PatternMatcher` |
| 7 | **Fraud History Check** | Flag customers with previous fraud flags | `PatternMatcher` |
| 8 | **6 High-Risk Countries** | NG, GH, RU, UA, VN, KH | `pattern_matcher.py` |
| 9 | **Pattern Hashing (MD5)** | Deduplication by amount bucket + country + merchant | `PatternMatcher` |
| 10 | **Composite Risk Scoring** | Weighted 40/30/30 formula with 4-tier levels | `PatternMatcher` |
| 11 | **Redis Risk Profile Cache** | 24h TTL customer profile caching | `RiskProfileCache` |
| 12 | **3-Tier Profile Lookup** | Redis → mock dict → default MEDIUM | `RiskProfileCache` |
| 13 | **5 Mock Customer Profiles** | LOW to CRITICAL with realistic data | `risk_profile.py` |
| 14 | **5 Known Fraud Patterns** | Cross-border, amount, velocity, merchant, night-time | `risk_profile.py` |
| 15 | **Keyword Pattern Matching** | Flag reason → fraud pattern similarity lookup | `get_similar_cases()` |
| 16 | **Default Unknown Customer** | Unknown IDs get MEDIUM risk (score=45) | `_DEFAULT_PROFILE` |
| 17 | **GPT-4o Streaming Analysis** | Real-time streamed fraud investigation reports | `FraudAnalyser` |
| 18 | **5-Section Structured Output** | FLAG REASON → RISK → PATTERN → ACTIONS → DECISION | `FRAUD_ANALYSIS_SYSTEM_PROMPT` |
| 19 | **4 Decision Outcomes** | DECLINE / HOLD FOR REVIEW / APPROVE WITH MONITORING / IMMEDIATE BLOCK | Prompt template |
| 20 | **Temperature 0.3** | Conservative financial analysis | `FraudAnalyser` |
| 21 | **Fallback Static Analysis** | 19-line static report when API unavailable | `_FALLBACK_ANALYSIS` |
| 22 | **50-char Chunk Streaming** | Fallback analysis chunked for SSE compatibility | `analyse_transaction()` |
| 23 | **Non-Streaming Mode** | Full JSON response via `stream=false` | `analyse_transaction_full()` |
| 24 | **SSE Event Format** | Server-Sent Events with metadata + chunks + [DONE] | `_event_generator()` |
| 25 | **Rich User Prompt** | Full transaction + profile + anomalies + patterns | `_build_user_message()` |
| 26 | **POST /api/v1/analyse** | Direct transaction analysis (stream or JSON) | `src/main.py` |
| 27 | **GET /api/v1/stream** | Live stream of latest event-hub transaction | `src/main.py` |
| 28 | **POST /api/v1/simulate** | Scenario-based simulation with full analysis | `src/main.py` |
| 29 | **GET /health** | Health check with mock_mode status | `src/main.py` |
| 30 | **CORS Middleware** | Allow all origins for development | `src/main.py` |
| 31 | **Structured JSON Logging** | structlog with ISO timestamps | `src/main.py` |
| 32 | **FastAPI Lifespan** | Async startup/shutdown for background tasks | `src/main.py` |
| 33 | **Background Task Pattern** | Event processor runs as asyncio.create_task | `lifespan()` |
| 34 | **Graceful Shutdown** | Event processor cancelled on app shutdown | `lifespan()` |
| 35 | **Pydantic Validation** | Constraint validation on all inputs | `src/models.py` |
| 36 | **Pydantic Settings** | `.env` file + environment variable config | `src/config.py` |
| 37 | **LRU-Cached Settings** | Singleton via `@lru_cache()` | `get_settings()` |
| 38 | **Docker Support** | Python 3.11 slim container | `infra/Dockerfile` |
| 39 | **Docker Compose** | 2-service stack (app + Redis) | `infra/docker-compose.yml` |
| 40 | **Redis Health Check** | `redis-cli ping` every 5s in compose | `docker-compose.yml` |
| 41 | **Complete Offline Mode** | Full pipeline works without ANY external service | `MOCK_MODE=true` |
| 42 | **20 Unit Tests** | 3 test classes covering all components | `tests/` |

---

## Prerequisites

<details>
<summary><strong>macOS</strong></summary>

```bash
# Python 3.11+
brew install python@3.11

# Verify
python3 --version    # Python 3.11.x

# Optional: Redis (for local cache)
brew install redis
brew services start redis

# Optional: Docker (for containerized deployment)
brew install --cask docker
```
</details>

<details>
<summary><strong>Windows</strong></summary>

```powershell
# Python 3.11+
winget install Python.Python.3.11

# Verify
python --version    # Python 3.11.x

# Optional: Redis (via WSL or Docker)
# No native Windows Redis — use Docker Compose instead

# Optional: Docker Desktop
winget install Docker.DockerDesktop
```
</details>

<details>
<summary><strong>Linux (Ubuntu/Debian)</strong></summary>

```bash
# Python 3.11+
sudo apt update && sudo apt install python3.11 python3.11-venv python3-pip

# Verify
python3.11 --version    # Python 3.11.x

# Optional: Redis
sudo apt install redis-server
sudo systemctl start redis

# Optional: Docker
sudo apt install docker.io docker-compose
```
</details>

### Service Dependencies

| Service | Purpose | Required? | Fallback |
|---------|---------|-----------|----------|
| Azure OpenAI (GPT-4o) | Streaming fraud analysis | ❌ | Static `_FALLBACK_ANALYSIS` |
| Redis | Customer risk profile cache | ❌ | In-memory `MOCK_PROFILES` (5 customers) |
| Azure Event Hubs | Real-time transaction events | ❌ | Mock generator (every 30s) |

**All services are optional.** With `MOCK_MODE=true` (default), the full pipeline runs without any external connectivity.

---

## Quick Start

### 1. Clone and Setup

```bash
git clone https://github.com/maneeshkumar52/fraud-analysis-assistant.git
cd fraud-analysis-assistant

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate    # macOS/Linux
# .venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment (Optional)

```bash
cp .env.example .env
# Edit .env if you have Azure OpenAI, Redis, or Event Hub credentials
# Default: MOCK_MODE=true — no Azure/Redis needed
```

### 3. Run the Server

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Test It

```bash
# Health check
curl http://localhost:8000/health

# Simulate a high-risk transaction
curl -s -X POST http://localhost:8000/api/v1/simulate \
  -H "Content-Type: application/json" \
  -d '{"scenario": "high_risk"}' | python -m json.tool

# Stream a velocity attack analysis
curl -s -N -X POST http://localhost:8000/api/v1/simulate \
  -H "Content-Type: application/json" \
  -d '{"scenario": "velocity"}'
```

### 5. Run the Demo

```bash
python demo_e2e.py
```

---

## Project Structure

```
fraud-analysis-assistant/
├── demo_e2e.py                          # End-to-end demo (all components)
├── requirements.txt                     # Python dependencies (10 packages)
├── pyproject.toml                       # Pytest configuration
├── .env.example                         # Environment variable template
├── src/                                 # Core application
│   ├── __init__.py
│   ├── main.py                          # FastAPI app, 4 endpoints, lifespan
│   ├── config.py                        # Pydantic Settings + OpenAI factory
│   ├── models.py                        # 5 Pydantic models + 1 Enum
│   ├── prompts.py                       # LLM system prompt (5-section format)
│   ├── pattern_matcher.py               # Rule-based anomaly detection
│   ├── risk_profile.py                  # Redis cache + 5 mock profiles
│   ├── analyser.py                      # GPT-4o streaming analysis
│   └── event_processor.py              # Event Hub consumer + mock
├── tests/                               # Test suite
│   ├── __init__.py
│   └── test_analyser.py                 # 20 tests, 3 classes, 3 fixtures
└── infra/                               # Deployment
    ├── Dockerfile                       # Python 3.11 slim image
    └── docker-compose.yml               # App + Redis stack
```

### Module Responsibility Matrix

| Module | Responsibility | Dependencies | Lines |
|--------|---------------|-------------|:-----:|
| `src/main.py` | FastAPI app, 4 endpoints, SSE streaming, lifespan | All src modules | 257 |
| `src/config.py` | Environment config + OpenAI client factory | `pydantic_settings`, `openai` | 35 |
| `src/models.py` | 5 data models + RiskLevel enum | `pydantic` | 56 |
| `src/prompts.py` | GPT-4o system prompt (5-section output format) | — | 29 |
| `src/pattern_matcher.py` | 4 anomaly rules + composite scoring | `models` | 102 |
| `src/risk_profile.py` | Redis cache, mock profiles, pattern lookup | `redis`, `models` | 262 |
| `src/analyser.py` | GPT-4o streaming + fallback analysis | `openai`, `config` | 150 |
| `src/event_processor.py` | Event Hub consumer + mock generator | `models`, `config` | 172 |
| `demo_e2e.py` | End-to-end component exercise | `src/*` | 104 |

---

## Configuration Reference

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `AZURE_OPENAI_ENDPOINT` | `https://placeholder.openai.azure.com/` | Only if `MOCK_MODE=false` | Azure OpenAI service endpoint |
| `AZURE_OPENAI_API_KEY` | `placeholder` | Only if `MOCK_MODE=false` | Azure OpenAI API key |
| `AZURE_OPENAI_DEPLOYMENT` | `gpt-4o` | ❌ | Chat completion deployment name |
| `AZURE_OPENAI_API_VERSION` | `2024-02-01` | ❌ | OpenAI API version |
| `REDIS_URL` | `redis://localhost:6379` | ❌ | Redis connection URL (mock fallback) |
| `EVENT_HUB_CONNECTION_STRING` | `placeholder` | ❌ | Azure Event Hub connection string |
| `EVENT_HUB_NAME` | `fraud-events` | ❌ | Event Hub topic name |
| `MOCK_MODE` | `true` | ❌ | Run without Azure/Redis dependencies |

---

## API Reference

### `GET /health`

Health check for container orchestrators.

**Response** `200 OK`:
```json
{
    "status": "healthy",
    "mock_mode": true,
    "service": "fraud-analysis-assistant",
    "version": "1.0.0"
}
```

### `POST /api/v1/analyse`

Analyse a flagged transaction with optional SSE streaming.

**Request Body**: `AnalysisRequest`
```json
{
    "transaction": {
        "transaction_id": "TXN-20250122-001",
        "customer_id": "CUST-001",
        "amount": 2450.00,
        "currency": "GBP",
        "merchant_name": "ElectroMart Lagos",
        "merchant_category": "Electronics",
        "location_country": "NG",
        "location_city": "Lagos",
        "timestamp": "2025-01-22T02:15:00Z",
        "flag_reason": "International transaction at unusual hour",
        "flag_score": 0.94
    },
    "stream": true
}
```

**Response (stream=true)**: `text/event-stream`
```
data: {"composite_risk_score": 0.82, "composite_risk_level": "CRITICAL", "anomalies": [...], ...}
data: {"chunk": "## FLAG REASON\n..."}
data: {"chunk": "..."}
data: [DONE]
```

**Response (stream=false)**: `application/json`
```json
{
    "transaction_id": "TXN-20250122-001",
    "customer_id": "CUST-001",
    "composite_risk_score": 0.82,
    "composite_risk_level": "CRITICAL",
    "anomalies": ["Amount £2,450.00 is 12.25x above typical max (£200.00)"],
    "matching_patterns": [{"pattern_id": "PAT-001", ...}],
    "analysis": "## FLAG REASON\n..."
}
```

### `POST /api/v1/simulate`

Generate and analyse a simulated transaction by scenario.

**Request Body**: `SimulateRequest`
```json
{"scenario": "high_risk"}    // "high_risk" | "low_risk" | "velocity"
```

**Response**: Full JSON with transaction, risk profile summary, scores, anomalies, patterns, and analysis.

### `GET /api/v1/stream`

Stream SSE analysis of the latest event-hub transaction. If no event received yet, auto-generates a `high_risk` simulation.

---

## Risk Scoring Engine

### Anomaly Detection Rules

| # | Rule | Trigger | Example |
|---|------|---------|---------|
| 1 | **Amount anomaly** | `amount > 2 × typical_transaction_range_max` | £2,450 vs max £200 → 12.25× |
| 2 | **Geographic anomaly** | Country/city not in `usual_locations` AND `risk_score < 60` | Lagos, NG for a London customer |
| 3 | **High-risk merchant** | Merchant category contains: casino, crypto, wire transfer, money order, pawnshop | CryptoExchange Pro |
| 4 | **Fraud history** | `previous_fraud_flags > 0` | 7 previous flags |

### High-Risk Countries

| Code | Country |
|------|---------|
| NG | Nigeria |
| GH | Ghana |
| RU | Russia |
| UA | Ukraine |
| VN | Vietnam |
| KH | Cambodia |

### Risk Level Thresholds

| Composite Score | Risk Level | Typical Action |
|:---------------:|:----------:|---------------|
| ≥ 0.75 | CRITICAL | Immediate block |
| ≥ 0.50 | HIGH | Hold for review |
| ≥ 0.25 | MEDIUM | Approve with monitoring |
| < 0.25 | LOW | Approve |

---

## Mock Data Catalog

### Customer Risk Profiles (5 pre-defined)

| Customer | Score | Level | Flags | Account Age | Profile |
|----------|:-----:|:-----:|:-----:|:-----------:|---------|
| CUST-001 | 15 | LOW | 0 | 1,825 days | Long-standing, regular spending £10–£200, London |
| CUST-002 | 72 | HIGH | 3 | 487 days | International transactions, crypto, 3 flags in 6 months |
| CUST-003 | 50 | MEDIUM | 0 | 180 days | New account, limited history, recent address change |
| CUST-004 | 28 | LOW | 1 | 2,190 days | Business account, payroll-sized transactions £50–£5,000 |
| CUST-005 | 91 | CRITICAL | 7 | 90 days | Under investigation, linked to known fraud network |
| Unknown | 45 | MEDIUM | 0 | 90 days | Default profile for unrecognised customer IDs |

### Fraud Patterns (5 known)

| Pattern | Name | Similarity | Cases | Keywords |
|---------|------|:----------:|:-----:|----------|
| PAT-001 | Cross-border card present | 0.92 | 1,247 | international, foreign, country, cross-border |
| PAT-002 | Amount anomaly | 0.87 | 3,821 | amount, typical, range, above, large, high |
| PAT-003 | Rapid velocity | 0.95 | 892 | velocity, rapid, multiple, minutes, fast |
| PAT-004 | High-risk merchant category | 0.78 | 567 | crypto, wire, money transfer, gambling, casino |
| PAT-005 | Night-time anomaly | 0.65 | 2,103 | night, overnight, 2am, 3am, 4am, 5am, midnight |

### Simulation Scenarios (3 pre-built)

| Scenario | Transaction | Amount | Location | Customer | Flag Score |
|----------|------------|:------:|----------|----------|:----------:|
| `high_risk` | TXN-001 ElectroMart Lagos | £2,450 | Lagos, NG | CUST-001 | 0.94 |
| `low_risk` | TXN-002 Tesco Express | £89.50 | London, GB | CUST-001 | 0.42 |
| `velocity` | TXN-003 CryptoExchange Pro | €750 | Amsterdam, NL | CUST-005 | 0.88 |

---

## Event Processing

### Azure Event Hubs (Production)

```
  Azure Event Hub: "fraud-events"
         │
         ▼
  EventHubConsumerClient
  (from_connection_string, $Default consumer group)
         │
         ▼
  Parse JSON → FlaggedTransaction
         │
         ▼
  callback(transaction) → full analysis pipeline
         │
         ▼
  Checkpoint updated (for partition offset tracking)
```

### Mock Processor (Development)

```
  _mock_processor (asyncio background task)
         │
         ├─ Pick random from SAMPLE_FLAGGED_TRANSACTIONS
         │
         ├─ callback(transaction) → full analysis pipeline
         │
         ├─ Sleep 30 seconds
         │
         └─ Loop until _running = False
```

---

## Testing

### Run Tests

```bash
pytest tests/ -v
```

### Test Suite (20 tests, 3 classes)

All tests run with `MOCK_MODE=true` — no Azure or Redis required.

| Test Class | Tests | What It Verifies |
|-----------|:-----:|-----------------|
| `TestPatternMatcher` | 6 | Normal → no anomalies; high amount → amount flag; crypto → merchant flag; composite score validity; high > low risk; pattern hash determinism |
| `TestRiskProfileCache` | 5 | CUST-001 → LOW; CUST-002 → HIGH + 3 flags; unknown → MEDIUM default; similar cases returns patterns; limit parameter respected |
| `TestEventHubProcessor` | 5 | high_risk → Lagos/NG; low_risk → London/GB; velocity → Amsterdam/NL; unknown → defaults to high_risk; mock_mode=True |

### Fixtures

| Fixture | Transaction | Key Properties |
|---------|------------|----------------|
| `normal_transaction` | £50 Tesco London | Low amount, domestic, known merchant |
| `high_amount_transaction` | £5,000 ElectroMart | 25× above typical max |
| `low_risk_profile` | CUST-001 | score=15, LOW, 0 flags |

---

## Deployment

### Docker Compose (Recommended)

```bash
cd infra
docker-compose up --build
```

This starts:
- **app** (port 8000): FastAPI fraud analysis service with `MOCK_MODE=true`
- **redis** (port 6379): Redis 7 Alpine with health checks every 5s

### Docker Only

```bash
cd infra
docker build -t fraud-analysis-assistant .
docker run -p 8000:8000 --env-file ../.env fraud-analysis-assistant
```

### Verify

```bash
curl http://localhost:8000/health
# {"status": "healthy", "mock_mode": true, "service": "fraud-analysis-assistant", "version": "1.0.0"}
```

---

## Troubleshooting

| Symptom | Cause | Solution |
|---------|-------|----------|
| Fallback analysis instead of GPT-4o | Azure OpenAI unreachable | Set `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_API_KEY` in `.env` |
| "HOLD FOR REVIEW" for everything | Using `_FALLBACK_ANALYSIS` (static) | Expected in mock mode; connect real Azure OpenAI for dynamic analysis |
| Redis connection failed in logs | Redis not running | Expected — system uses `MOCK_PROFILES` automatically |
| No events from Event Hub | Connection string is placeholder | Expected with `MOCK_MODE=true`; mock generator emits every 30s |
| Unknown customer always MEDIUM | Customer not in MOCK_PROFILES | Expected — `_DEFAULT_PROFILE` assigns score=45 MEDIUM |
| Composite score doesn't match manual calc | Anomaly count capped at 5 | Formula uses `min(anomaly_count/5, 1.0)` — max contribution is 0.30 |
| SSE stream hangs | Proxy buffering enabled | Set `X-Accel-Buffering: no` header (already set by app) |
| `ImportError: azure.eventhub` | SDK not installed | `pip install azure-eventhub` (only for production Event Hub) |
| Tests fail with import errors | Missing test dependencies | `pip install pytest pytest-asyncio` |
| Port 8000 already in use | Another service on 8000 | `uvicorn src.main:app --port 8001` |

---

## Azure Production Mapping

| Local Component | Azure Production Service | Purpose |
|----------------|-------------------------|---------|
| `uvicorn src.main:app` | Azure Container Apps | Serverless container hosting |
| `AsyncAzureOpenAI` | Azure OpenAI Service (GPT-4o) | Streaming fraud analysis |
| `redis.asyncio` | Azure Cache for Redis | Risk profile caching (24h TTL) |
| `EventHubConsumerClient` | Azure Event Hubs | Real-time transaction ingestion |
| `.env` file | Azure Key Vault | Secrets management |
| `structlog` JSON output | Application Insights + Log Analytics | Observability |
| `Dockerfile` | Azure Container Registry | Image storage |
| `docker-compose.yml` | Azure Container Apps environment | Multi-container orchestration |
| — | Azure Monitor Alerts | SLA + anomaly monitoring |
| — | Azure API Management | Rate limiting, authentication |
| — | Azure AD (Entra ID) | Investigator authentication |

---

## Production Checklist

### Security

| # | Item | Status | Notes |
|---|------|--------|-------|
| 1 | Remove `allow_origins=["*"]` CORS | ⬜ | Restrict to investigation dashboard origin |
| 2 | Add API authentication | ⬜ | JWT/API key for `/analyse` and `/simulate` |
| 3 | Replace env vars with Key Vault | ⬜ | `DefaultAzureCredential` + Key Vault references |
| 4 | Add rate limiting | ⬜ | Azure API Management or FastAPI middleware |
| 5 | Validate transaction input sanitisation | ⬜ | Prevent prompt injection via merchant_name/flag_reason |
| 6 | Encrypt Redis connections | ⬜ | TLS for Azure Cache for Redis |

### Reliability

| # | Item | Status | Notes |
|---|------|--------|-------|
| 7 | Add circuit breaker for OpenAI | ⬜ | `tenacity` with exponential backoff |
| 8 | Event Hub checkpointing to Blob Storage | ⬜ | Required for at-least-once processing |
| 9 | Dead letter queue for failed events | ⬜ | Failed transactions → separate queue |
| 10 | Redis connection pooling | ⬜ | Pool size tuning for concurrent load |
| 11 | Health check for Redis on startup | ⬜ | Verify connectivity before serving |

### Observability

| # | Item | Status | Notes |
|---|------|--------|-------|
| 12 | Dashboard: transactions/min, risk distribution | ⬜ | Azure Monitor Workbook |
| 13 | Alert: CRITICAL risk rate > threshold | ⬜ | Sudden spike = potential attack |
| 14 | Alert: fallback analysis rate > 10% | ⬜ | OpenAI service degradation |
| 15 | Log analytics: pattern match accuracy | ⬜ | Tune anomaly thresholds over time |

### Data

| # | Item | Status | Notes |
|---|------|--------|-------|
| 16 | Replace mock profiles with real customer DB | ⬜ | Customer risk profile API integration |
| 17 | Replace mock patterns with ML model | ⬜ | Trained fraud pattern detector |
| 18 | Transaction audit logging | ⬜ | Every analysis → persistent audit trail |
| 19 | PII/PCI compliance for card data | ⬜ | Never log full card numbers |

---

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| **Runtime** | Python | 3.11+ |
| **Web Framework** | FastAPI | 0.115.0 |
| **ASGI Server** | Uvicorn | 0.30.6 |
| **LLM** | Azure OpenAI (GPT-4o) | API 2024-02-01 |
| **Caching** | Redis | 7 Alpine |
| **Event Streaming** | Azure Event Hubs | — |
| **Validation** | Pydantic | 2.9.2 |
| **Configuration** | pydantic-settings | 2.5.2 |
| **Logging** | structlog | 24.4.0 |
| **HTTP Client** | httpx | 0.27.2 |
| **Testing** | pytest + pytest-asyncio | 8.3.3 / 0.24.0 |
| **Container** | Docker (Python 3.11 slim) | — |
| **Orchestration** | Docker Compose | — |

---

## License

MIT — see [LICENSE](LICENSE) for details.

---

<div align="center">

**Built by [Maneesh Kumar](https://github.com/maneeshkumar52)**

*Prompt to Production — Chapter 19, Project 4*

*Real-time financial fraud analysis with rule-based anomaly detection, GPT-4o streaming investigation reports, and complete offline capability.*

</div>