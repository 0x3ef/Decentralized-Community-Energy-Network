"""Compatibility entry point for the blockchain outbox worker."""

from src.workers.blockchain_worker import run

__all__ = ["run"]
