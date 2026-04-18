# Fraud Analysis Assistant

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

Fraud analysis platform for transaction risk triage, anomaly detection, and investigation-ready outputs — powered by Azure OpenAI, Redis caching, and Azure Event Hubs for real-time streaming.

## Architecture

```
Transaction Events
        │
        ├──► Event Hub (real-time stream)
        │         │
        │         ▼
        │    EventHubProcessor
        │         │
        ▼         ▼
┌───────────────────────────────────────┐
│  FastAPI Service (:8000)              │
│                                       │
│  /analyse   ──► FraudAnalyser        │──► GPT-4o risk assessment
│  /simulate  ──► PatternMatcher       │──► Rule-based pattern detection
│  /stream    ──► SSE streaming        │──► Real-time flagged transactions
│                                       │
│  RiskProfileCache ──► Redis          │──► Cached risk profiles per account
└───────────────────────────────────────┘
```

## Key Features

- **AI-Powered Analysis** — GPT-4o analyzes transactions with structured risk assessments and investigation recommendations
- **Pattern Matching** — Rule-based detection engine for known fraud patterns (velocity checks, geo-anomalies, amount thresholds)
- **Risk Profile Caching** — Redis-backed per-account risk profiles with historical scoring
- **Real-Time Streaming** — Azure Event Hub integration with Server-Sent Events (SSE) for live transaction monitoring
- **Transaction Simulation** — `/simulate` endpoint for testing fraud detection rules against synthetic data
- **MOCK_MODE** — Full pipeline runs locally without Azure/Redis dependencies
- **Structured Prompts** — Reusable prompt templates in `prompts.py` for consistent LLM analysis

## Step-by-Step Flow

### Step 1: Transaction Ingestion
Transactions arrive via `POST /analyse` (batch) or Azure Event Hub (streaming). `EventHubProcessor` processes real-time events.

### Step 2: Pattern Matching
`PatternMatcher` applies rule-based checks: velocity thresholds, geographic anomalies, amount deviations, and known fraud indicators.

### Step 3: Risk Profile Lookup
`RiskProfileCache` fetches the account's historical risk profile from Redis, including past flags, average transaction amount, and risk score.

### Step 4: AI Analysis
`FraudAnalyser` sends the transaction context (pattern match results, risk profile, transaction details) to GPT-4o for structured risk assessment.

### Step 5: Flagging & Response
Returns `FlaggedTransaction` with risk_score, risk_level, matched_patterns, ai_reasoning, and recommended_action (approve/review/block).

### Step 6: Live Monitoring
`GET /stream` provides SSE endpoint for real-time flagged transaction updates.

## Repository Structure

```
fraud-analysis-assistant/
├── src/
│   ├── main.py              # FastAPI app with /analyse, /simulate, /stream
│   ├── analyser.py           # FraudAnalyser — GPT-4o risk assessment
│   ├── pattern_matcher.py    # PatternMatcher — rule-based detection
│   ├── risk_profile.py       # RiskProfileCache — Redis-backed profiles
│   ├── event_processor.py    # EventHubProcessor — real-time stream
│   ├── prompts.py            # Structured LLM prompt templates
│   ├── models.py             # AnalysisRequest, FlaggedTransaction, etc.
│   └── config.py             # Environment settings
├── tests/
│   └── test_analyser.py
├── infra/
│   ├── Dockerfile
│   └── docker-compose.yml    # App + Redis
├── demo_e2e.py
├── pyproject.toml
├── requirements.txt
└── .env.example
```

## Quick Start

```bash
git clone https://github.com/maneeshkumar52/fraud-analysis-assistant.git
cd fraud-analysis-assistant
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Set MOCK_MODE=true for local testing
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_OPENAI_ENDPOINT` | Yes | Azure OpenAI endpoint |
| `AZURE_OPENAI_DEPLOYMENT` | Yes | Model deployment (gpt-4o) |
| `MOCK_MODE` | No | Run without Azure/Redis (default: true) |
| `REDIS_URL` | No | Redis connection URL |
| `EVENT_HUB_CONNECTION_STRING` | No | Azure Event Hub connection |
| `EVENT_HUB_NAME` | No | Event Hub name (fraud-events) |

## Testing

```bash
pytest -q
python demo_e2e.py
```

## License

MIT
