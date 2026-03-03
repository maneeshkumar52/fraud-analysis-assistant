from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import structlog
import json
import asyncio
from typing import AsyncGenerator

from .models import AnalysisRequest, SimulateRequest, FlaggedTransaction
from .analyser import FraudAnalyser
from .risk_profile import RiskProfileCache
from .pattern_matcher import PatternMatcher
from .event_processor import EventHubProcessor
from .config import get_settings

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Application state shared across request handlers
# ---------------------------------------------------------------------------
_risk_cache: RiskProfileCache = RiskProfileCache()
_pattern_matcher: PatternMatcher = PatternMatcher()
_event_processor: EventHubProcessor = EventHubProcessor()
_latest_transaction: FlaggedTransaction | None = None


async def _on_new_transaction(transaction: FlaggedTransaction) -> None:
    """Background callback: store the latest event-hub transaction for the demo endpoint."""
    global _latest_transaction
    _latest_transaction = transaction
    logger.info(
        "main.new_transaction",
        transaction_id=transaction.transaction_id,
    )


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background tasks on startup; clean up on shutdown."""
    logger.info("app.startup")

    # Pre-populate Redis (fire-and-forget; failure is non-fatal)
    asyncio.create_task(_risk_cache.populate_redis())

    # Start the event-hub processor in the background
    processor_task = asyncio.create_task(
        _event_processor.start_processing(_on_new_transaction)
    )

    yield

    logger.info("app.shutdown")
    _event_processor.stop()
    processor_task.cancel()
    try:
        await processor_task
    except asyncio.CancelledError:
        pass


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
settings = get_settings()

app = FastAPI(
    title="Fraud Analysis Assistant",
    description=(
        "Real-time fraud analysis with streaming GPT-4o responses, "
        "Redis risk profiles, and Azure Event Hubs event processing. "
        "Project 9, Chapter 20 of 'Prompt to Production' by Maneesh Kumar."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helper: build SSE event generator
# ---------------------------------------------------------------------------
async def _event_generator(
    transaction: FlaggedTransaction,
) -> AsyncGenerator[str, None]:
    """Yield SSE-formatted chunks for a full fraud analysis."""
    risk_profile = await _risk_cache.get_profile(transaction.customer_id)
    patterns = await _risk_cache.get_similar_cases(
        transaction.amount, transaction.flag_reason
    )
    anomalies = _pattern_matcher.detect_anomalies(transaction, risk_profile)
    composite_score, composite_level = _pattern_matcher.calculate_composite_risk_score(
        transaction, risk_profile, anomalies
    )

    # Send enrichment metadata as the first SSE event
    metadata = {
        "event": "metadata",
        "transaction_id": transaction.transaction_id,
        "customer_id": transaction.customer_id,
        "composite_risk_score": composite_score,
        "composite_risk_level": composite_level,
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
        "matching_patterns": [p.pattern_name for p in patterns],
    }
    yield f"data: {json.dumps(metadata)}\n\n"

    analyser = FraudAnalyser()
    async for chunk in analyser.analyse_transaction(
        transaction, risk_profile, patterns, anomalies
    ):
        if chunk:
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"

    yield "data: [DONE]\n\n"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.post("/api/v1/analyse")
async def analyse(request: AnalysisRequest):
    """Analyse a flagged transaction.

    - **stream=true**: returns a Server-Sent Events stream (text/event-stream).
    - **stream=false**: returns the full analysis as a JSON object.
    """
    transaction = request.transaction
    logger.info(
        "api.analyse",
        transaction_id=transaction.transaction_id,
        stream=request.stream,
    )

    if request.stream:
        return StreamingResponse(
            _event_generator(transaction),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # Non-streaming: accumulate full analysis
    risk_profile = await _risk_cache.get_profile(transaction.customer_id)
    patterns = await _risk_cache.get_similar_cases(
        transaction.amount, transaction.flag_reason
    )
    anomalies = _pattern_matcher.detect_anomalies(transaction, risk_profile)
    composite_score, composite_level = _pattern_matcher.calculate_composite_risk_score(
        transaction, risk_profile, anomalies
    )

    analyser = FraudAnalyser()
    full_text = await analyser.analyse_transaction_full(
        transaction, risk_profile, patterns, anomalies
    )

    return {
        "transaction_id": transaction.transaction_id,
        "customer_id": transaction.customer_id,
        "composite_risk_score": composite_score,
        "composite_risk_level": composite_level,
        "anomalies": anomalies,
        "matching_patterns": [p.pattern_name for p in patterns],
        "analysis": full_text,
    }


@app.get("/api/v1/stream")
async def stream_latest():
    """Stream the fraud analysis for the latest event-hub transaction (demo endpoint).

    If no transaction has been received yet, uses a built-in high-risk example.
    """
    transaction = _latest_transaction
    if transaction is None:
        # Use the first sample transaction as a sensible default
        processor = EventHubProcessor()
        transaction = await processor.generate_simulated_transaction("high_risk")

    logger.info("api.stream_latest", transaction_id=transaction.transaction_id)

    return StreamingResponse(
        _event_generator(transaction),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/v1/simulate")
async def simulate(request: SimulateRequest):
    """Generate and analyse a simulated flagged transaction.

    Supported scenarios: **high_risk**, **low_risk**, **velocity**.
    Returns the full analysis as JSON (no streaming).
    """
    logger.info("api.simulate", scenario=request.scenario)

    processor = EventHubProcessor()
    transaction = await processor.generate_simulated_transaction(request.scenario)

    risk_profile = await _risk_cache.get_profile(transaction.customer_id)
    patterns = await _risk_cache.get_similar_cases(
        transaction.amount, transaction.flag_reason
    )
    anomalies = _pattern_matcher.detect_anomalies(transaction, risk_profile)
    composite_score, composite_level = _pattern_matcher.calculate_composite_risk_score(
        transaction, risk_profile, anomalies
    )

    analyser = FraudAnalyser()
    full_text = await analyser.analyse_transaction_full(
        transaction, risk_profile, patterns, anomalies
    )

    return {
        "scenario": request.scenario,
        "transaction": transaction.model_dump(),
        "risk_profile_summary": {
            "customer_id": risk_profile.customer_id,
            "risk_score": risk_profile.risk_score,
            "risk_level": risk_profile.risk_level,
            "previous_fraud_flags": risk_profile.previous_fraud_flags,
        },
        "composite_risk_score": composite_score,
        "composite_risk_level": composite_level,
        "anomalies": anomalies,
        "matching_patterns": [p.pattern_name for p in patterns],
        "analysis": full_text,
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "mock_mode": settings.mock_mode,
        "service": "fraud-analysis-assistant",
        "version": "1.0.0",
    }
