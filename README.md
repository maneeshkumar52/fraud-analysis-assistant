# fraud-analysis-assistant

Real-time fraud analysis with streaming GPT-4o responses, Redis risk profiles,
and Azure Event Hubs event processing.

**Project 9, Chapter 20 of "Prompt to Production" by Maneesh Kumar**

---

## Overview

When the rule-based fraud engine flags a transaction, this service provides
context-enriched AI analysis within 2 seconds:

- **Why** the transaction was flagged
- **What** historical patterns match
- **Recommended** investigation steps

Responses are streamed via Server-Sent Events (SSE) for low-latency delivery
to fraud analyst dashboards.

---

## Architecture

```
Transaction Flag
      |
      v
Azure Event Hubs
      |
      v
EventHubProcessor
      |
      +---> RiskProfileCache (Redis)
      |           |
      |           +---> Customer risk score, typical ranges, fraud history
      |
      +---> PatternMatcher
      |           |
      |           +---> Anomaly detection, composite risk score
      |
      v
FraudAnalyser (GPT-4o streaming)
      |
      v
SSE Response --> Analyst Dashboard
```

---

## Quick Start (Mock Mode — no Azure credentials needed)

### 1. Clone and install

```bash
git clone <repo>
cd fraud-analysis-assistant
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# MOCK_MODE=true is the default — no Azure keys needed for local development
```

### 3. Run the API

```bash
uvicorn src.main:app --reload --port 8000
```

The API will be available at http://localhost:8000
Interactive docs: http://localhost:8000/docs

---

## Docker Compose (App + Redis)

```bash
docker compose -f infra/docker-compose.yml up --build
```

---

## API Endpoints

### POST /api/v1/analyse — Streaming SSE analysis

```bash
curl -N -X POST http://localhost:8000/api/v1/analyse \
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
      "timestamp": "2025-01-22T03:17:42Z",
      "flag_reason": "International transaction in high-risk country, 12x above typical amount",
      "flag_score": 0.94
    },
    "stream": true
  }'
```

SSE events are formatted as:
```
data: {"event": "metadata", "transaction_id": "...", "composite_risk_score": 0.73, ...}

data: {"chunk": "## FLAG REASON\n"}

data: {"chunk": "This transaction was flagged because..."}

data: [DONE]
```

### POST /api/v1/analyse — Full JSON (non-streaming)

```bash
curl -X POST http://localhost:8000/api/v1/analyse \
  -H "Content-Type: application/json" \
  -d '{"transaction": {...}, "stream": false}'
```

### GET /api/v1/stream — Stream analysis of the latest event-hub transaction

```bash
curl -N http://localhost:8000/api/v1/stream
```

### POST /api/v1/simulate — Simulate a scenario and get full analysis

```bash
curl -X POST http://localhost:8000/api/v1/simulate \
  -H "Content-Type: application/json" \
  -d '{"scenario": "high_risk"}'
```

Supported scenarios: `high_risk`, `low_risk`, `velocity`

### GET /health — Health check

```bash
curl http://localhost:8000/health
```

---

## Running Tests

```bash
pytest
```

All tests run without Azure credentials using mock data (MOCK_MODE=true).

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | placeholder | Your Azure OpenAI endpoint |
| `AZURE_OPENAI_API_KEY` | placeholder | Your Azure OpenAI API key |
| `AZURE_OPENAI_DEPLOYMENT` | gpt-4o | Deployment name |
| `AZURE_OPENAI_API_VERSION` | 2024-02-01 | API version |
| `REDIS_URL` | redis://localhost:6379 | Redis connection URL |
| `EVENT_HUB_CONNECTION_STRING` | placeholder | Azure Event Hubs connection string |
| `EVENT_HUB_NAME` | fraud-events | Event Hub name |
| `MOCK_MODE` | true | Use mock data instead of real Azure services |

---

## Mock Customer Profiles

The following customer IDs are pre-loaded for local development:

| Customer ID | Risk Score | Risk Level | Notes |
|---|---|---|---|
| CUST-001 | 15 | LOW | Long-standing customer, regular patterns |
| CUST-002 | 72 | HIGH | 3 fraud flags, international transactions |
| CUST-003 | 50 | MEDIUM | New account, limited history |
| CUST-004 | 28 | LOW | Business account |
| CUST-005 | 91 | CRITICAL | Under investigation |

---

## Project Reference

This is **Project 9** from **Chapter 20** of:

> *Prompt to Production: Building Production AI Applications*
> by **Maneesh Kumar**

The project demonstrates:
- Real-time AI analysis of financial fraud events
- GPT-4o streaming via Server-Sent Events for sub-2-second UX
- Redis-backed risk profile enrichment
- Azure Event Hubs integration with graceful mock fallback
- Production patterns: structured logging, graceful degradation, health checks
