"""
tests/unit/test_graceful.py
Tests for utils/graceful.py — run_module timeout and error capture.
"""
import asyncio
import pytest

from models.schemas import ModuleStatus
from utils.graceful import run_module


# ── Success path ────────────────────────────────────────────────────────────

async def test_run_module_success() -> None:
    """run_module with a coroutine that returns a value → (value, ModuleStatus OK)."""
    async def _ok():
        return 42

    result, status = await run_module("test_mod", _ok())
    assert result == 42
    assert isinstance(status, ModuleStatus)
    assert status.status == "OK"
    assert status.error is None


# ── Timeout path ────────────────────────────────────────────────────────────

async def test_run_module_timeout() -> None:
    """run_module with a long-running coroutine and tiny timeout → error status."""
    async def _slow():
        await asyncio.sleep(999)
        return "never"

    result, status = await run_module("slow_mod", _slow(), timeout=0.01)
    assert result is None
    assert status.status == "INCOMPLETE"
    assert status.error is not None
    assert "Timed out" in status.error


# ── Exception path ──────────────────────────────────────────────────────────

async def test_run_module_exception_does_not_propagate() -> None:
    """run_module with a coroutine that raises → error captured, does not propagate."""
    async def _boom():
        raise ValueError("intentional error")

    result, status = await run_module("boom_mod", _boom())
    assert result is None
    assert status.status == "INCOMPLETE"
    assert status.error is not None
    assert "ValueError" in status.error
