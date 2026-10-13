"""Offline scoring / grouping engine (no network, no LLM)."""
from . import query, diagnose, apply

__all__ = ["query", "diagnose", "apply"]
