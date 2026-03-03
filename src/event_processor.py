import asyncio
import json
import random
import structlog
from datetime import datetime, timezone
from typing import Optional, Callable, Awaitable
from .models import FlaggedTransaction
from .config import get_settings

logger = structlog.get_logger()

SAMPLE_FLAGGED_TRANSACTIONS = [
    {
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
        "flag_score": 0.94,
    },
    {
        "transaction_id": "TXN-20250122-002",
        "customer_id": "CUST-001",
        "amount": 89.50,
        "currency": "GBP",
        "merchant_name": "Tesco Express",
        "merchant_category": "Grocery",
        "location_country": "GB",
        "location_city": "London",
        "timestamp": "2025-01-22T14:32:11Z",
        "flag_reason": "Possible false positive - within normal range but flagged by velocity rule",
        "flag_score": 0.42,
    },
    {
        "transaction_id": "TXN-20250122-003",
        "customer_id": "CUST-002",
        "amount": 750.00,
        "currency": "EUR",
        "merchant_name": "CryptoExchange Pro",
        "merchant_category": "Cryptocurrency",
        "location_country": "NL",
        "location_city": "Amsterdam",
        "timestamp": "2025-01-22T01:45:22Z",
        "flag_reason": "Crypto exchange transaction, velocity flag - 3rd transaction in 8 minutes",
        "flag_score": 0.88,
    },
]

# Map scenario names to sample transaction indices
_SCENARIO_INDEX = {
    "high_risk": 0,
    "low_risk": 1,
    "velocity": 2,
}


class EventHubProcessor:
    """Consumes flagged transactions from Azure Event Hubs or a mock generator."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.mock_mode: bool = self.settings.mock_mode
        self._running: bool = False

    async def start_processing(
        self,
        callback: Callable[[FlaggedTransaction], Awaitable[None]],
    ) -> None:
        """Start consuming events. Uses mock mode when MOCK_MODE=true or when the
        Azure Event Hubs SDK is not installed."""
        if self.mock_mode:
            logger.info("event_processor.mock_mode_start")
            await self._mock_processor(callback)
            return

        # Attempt to use the real Azure SDK
        try:
            from azure.eventhub.aio import EventHubConsumerClient  # type: ignore

            await self._real_processor(callback, EventHubConsumerClient)
        except ImportError:
            logger.warning(
                "event_processor.sdk_missing",
                package="azure-eventhub",
                fallback="mock_mode",
            )
            await self._mock_processor(callback)

    async def _real_processor(
        self,
        callback: Callable[[FlaggedTransaction], Awaitable[None]],
        EventHubConsumerClient,  # type: ignore
    ) -> None:
        """Consume events from Azure Event Hubs and invoke the callback."""
        s = self.settings
        client = EventHubConsumerClient.from_connection_string(
            s.event_hub_connection_string,
            consumer_group="$Default",
            eventhub_name=s.event_hub_name,
        )
        self._running = True
        logger.info(
            "event_processor.real_start",
            event_hub=s.event_hub_name,
        )

        async def on_event(partition_context, event):
            try:
                payload = json.loads(event.body_as_str())
                transaction = FlaggedTransaction(**payload)
                logger.info(
                    "event_processor.received",
                    transaction_id=transaction.transaction_id,
                    partition=partition_context.partition_id,
                )
                await callback(transaction)
                await partition_context.update_checkpoint(event)
            except Exception as exc:
                logger.error(
                    "event_processor.parse_error",
                    error=str(exc),
                )

        async with client:
            await client.receive(on_event=on_event, starting_position="-1")

    async def _mock_processor(
        self,
        callback: Callable[[FlaggedTransaction], Awaitable[None]],
    ) -> None:
        """Emit a random sample transaction every 30 seconds."""
        self._running = True
        logger.info("event_processor.mock_running", interval_seconds=30)
        while self._running:
            sample = random.choice(SAMPLE_FLAGGED_TRANSACTIONS)
            transaction = FlaggedTransaction(**sample)
            logger.info(
                "event_processor.mock_emit",
                transaction_id=transaction.transaction_id,
            )
            try:
                await callback(transaction)
            except Exception as exc:
                logger.error("event_processor.callback_error", error=str(exc))
            await asyncio.sleep(30)

    def stop(self) -> None:
        """Signal the processor to stop after the current iteration."""
        self._running = False
        logger.info("event_processor.stop_requested")

    async def generate_simulated_transaction(
        self, scenario: str = "high_risk"
    ) -> FlaggedTransaction:
        """Return a pre-defined sample transaction for the given scenario.

        Supported scenarios: "high_risk", "low_risk", "velocity".
        Defaults to "high_risk" for unknown scenario names.
        """
        index = _SCENARIO_INDEX.get(scenario, 0)
        sample = SAMPLE_FLAGGED_TRANSACTIONS[index]
        logger.info(
            "event_processor.simulate",
            scenario=scenario,
            transaction_id=sample["transaction_id"],
        )
        return FlaggedTransaction(**sample)
