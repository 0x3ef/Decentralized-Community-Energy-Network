"""Run outside the API: interval processing and durable community chain outbox."""

import asyncio
import logging
import signal
from src.core.observability import heartbeat, configure_logging
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
    from src.modules.settlement.worker import NativeSettlementWorker
    from src.core.config import Config
    native = NativeSettlementWorker()
    try:
        while not stop.is_set():
            try:
                async with AsyncSessionFactory() as session:
                    await processor.process_pending(session)
                    await processor.finalize_closed_intervals(session)
                if Config.NATIVE_SETTLEMENT_ENABLED:
                    await native.run_once(AsyncSessionFactory)
                if Config.LEGACY_SETTLEMENT_ENABLED:
                    await chain.audit_confirmed(AsyncSessionFactory)
                    await chain.process_outbox(AsyncSessionFactory)
                    await chain.sync_events(AsyncSessionFactory)
                await heartbeat("worker")
            except Exception as exc:
                await heartbeat("worker",False,error_code=type(exc).__name__)
                logger.exception("Community worker iteration failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=2)
            except TimeoutError:
                pass
    finally:
        await dispose_engine()


if __name__ == "__main__":
    configure_logging()
    asyncio.run(run())
