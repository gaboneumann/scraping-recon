"""
utils/graceful.py
Wraps async module coroutines with timeout and structured error capture.
All modules are invoked through run_module() — never called directly.
"""
import asyncio
import traceback
from typing import Any, Coroutine

from models.schemas import ModuleStatus


async def run_module(
    name: str,
    coro: Coroutine[Any, Any, Any],
    timeout: float = 20.0,
) -> tuple[Any | None, ModuleStatus]:
    """
    Execute a module coroutine with timeout and exception capture.

    Returns:
        (result, ModuleStatus) — result is None on failure.
    """
    try:
        result = await asyncio.wait_for(coro, timeout=timeout)
        return result, ModuleStatus(name=name, status="OK")
    except asyncio.TimeoutError:
        return None, ModuleStatus(
            name=name,
            status="INCOMPLETE",
            error=f"Timed out after {timeout}s",
        )
    except Exception:
        return None, ModuleStatus(
            name=name,
            status="INCOMPLETE",
            error=traceback.format_exc(limit=3),
        )
