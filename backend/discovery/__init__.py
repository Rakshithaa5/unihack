"""
backend/discovery/__init__.py
Exports the public interface for the discovery module.

Phase 1: real discover() from agent.py replaces the Phase 0.5 stub.
The stub is still importable via `backend.discovery.stub` for reference.
"""
from .agent import discover  # noqa: F401
