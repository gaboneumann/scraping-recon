"""
config.py
Settings and defaults for scraping_recon.
Always passed as an explicit parameter — never accessed as global state.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Config:
    """Runtime configuration for a single scan."""

    timeout: float = 15.0
    ua: str | None = None          # Override User-Agent (None = use UA_CHROME)
    verbose: bool = False
    no_color: bool = False
    skip_modules: list[str] = field(default_factory=list)
    deep: bool = False             # Enable Playwright for XHR interception
    output: str | None = None      # JSON output file path
