"""Periodic energy aggregation worker."""

from __future__ import annotations

import asyncio
import logging

from src.core.db import AsyncSessionFactory
from src.modules.energy.processor import EnergyProcessor

logger = logging.getLogger(__name__)


async def run(poll_seconds: float = 2.0) -> None:
    """Process raw telemetry and finalize expired energy intervals."""
    processor = EnergyProcessor()
    logger.info("Energy processing worker started")
    while True:
        try:
            async with AsyncSessionFactory() as session:
                processed = await processor.process_pending(session)
            async with AsyncSessionFactory() as session:
                credits = await processor.finalize_closed_intervals(session)
            if processed or credits:
                logger.info(
                    "Energy worker processed=%s credits_created=%s",
                    processed, credits,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Energy worker cycle failed")
        await asyncio.sleep(poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
