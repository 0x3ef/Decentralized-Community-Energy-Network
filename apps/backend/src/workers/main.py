"""Entry point for the blockchain outbox and confirmation worker."""

import asyncio
import logging

from src.workers.blockchain_worker import run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


if __name__ == "__main__":
    asyncio.run(run())
