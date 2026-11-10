"""Run outside the API: interval processing and durable community chain outbox."""

import asyncio
import logging
import signal
from src.core.db import AsyncSessionFactory, dispose_engine
from src.modules.community.chain import CommunityChain
from src.modules.energy.processor import EnergyProcessor

logger = logging.getLogger(__name__)


async def run():
    stop = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    processor = EnergyProcessor()
    chain = CommunityChain()
    try:
        while not stop.is_set():
            try:
                async with AsyncSessionFactory() as session:
                    await processor.process_pending(session)
                    await processor.finalize_closed_intervals(session)
                await chain.audit_confirmed(AsyncSessionFactory)
                await chain.process_outbox(AsyncSessionFactory)
                await chain.sync_events(AsyncSessionFactory)
            except Exception:
                logger.exception("Community worker iteration failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=2)
            except TimeoutError:
                pass
    finally:
        await dispose_engine()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
