"""
main.py
CLI entry point for scraping_recon. Built with Typer.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone
from typing import Optional

import typer
from rich.console import Console

logger = logging.getLogger(__name__)

from config import Config
from models.schemas import ModuleStatus, ReconReport
from modules.antibot import analyze_antibot
from modules.api_detector import detect_apis
from modules.auth_detector import detect_auth
from modules.classifier import classify_page, _detect_deep_ecommerce
from modules.legal import analyze_legal
from modules.pagination import detect_pagination
from modules.recommender import build_recommendation
from report.json_export import save_json, to_json
from report.terminal import render
from utils.graceful import run_module

app = typer.Typer(help="scraping_recon — pre-scraping reconnaissance tool")


@app.command()
def scan(
    url: str = typer.Option(..., "--url", "-u", help="Target URL to scan"),
    module: Optional[str] = typer.Option(None, "--module", "-m", help="Run a single module"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save JSON to file"),
    timeout: float = typer.Option(15.0, "--timeout", help="Per-request timeout in seconds"),
    ua: Optional[str] = typer.Option(None, "--ua", help="Override User-Agent"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show raw HTTP details"),
    no_color: bool = typer.Option(False, "--no-color", help="Disable rich colors"),
    skip: Optional[str] = typer.Option(None, "--skip", help="Comma-separated modules to skip"),
    deep: bool = typer.Option(False, "--deep", help="Enable Playwright XHR interception"),
) -> None:
    """Run a full recon scan on the target URL."""
    config = Config(
        timeout=timeout,
        ua=ua,
        verbose=verbose,
        no_color=no_color,
        skip_modules=[s.strip() for s in (skip or "").split(",") if s.strip()],
        deep=deep,
        output=output,
    )

    console = Console(no_color=no_color)

    if not json_output:
        console.print(f"[dim]Scanning {url} ...[/dim]")

    report = asyncio.run(_run_scan(url, config, module))

    if json_output or output:
        json_str = to_json(report)
        if output:
            save_json(report, output)
            if not json_output:
                console.print(f"[green]Report saved to {output}[/green]")
        if json_output:
            print(json_str)
    else:
        render(report, console=console)


async def _run_scan(
    url: str,
    config: Config,
    single_module: str | None = None,
) -> ReconReport:
    """Orchestrate all modules and build the ReconReport."""
    start = datetime.now(timezone.utc)
    import time
    t0 = time.monotonic()

    skip = set(config.skip_modules)

    def should_run(name: str) -> bool:
        if single_module:
            return name == single_module
        return name not in skip

    # Phase 1: independent modules run concurrently
    phase1_tasks = []
    phase1_names = []

    for name, coro in [
        ("legal",         analyze_legal(url, config.timeout)),
        ("classifier",    classify_page(url, config.timeout)),
        ("auth_detector", detect_auth(url, config.timeout)),
        ("api_detector",  detect_apis(url, config.timeout)),
        ("pagination",    detect_pagination(url, config.timeout)),
    ]:
        if should_run(name):
            phase1_tasks.append(run_module(name, coro))
            phase1_names.append(name)

    phase1_results = await asyncio.gather(*phase1_tasks)

    # Extract classifier result and api_detector endpoints
    classifier_result = None
    api_endpoints_for_probe = None
    for name, (result, status) in zip(phase1_names, phase1_results):
        if name == "classifier" and status.status == "OK" and result:
            classifier_result = result
        elif name == "api_detector" and status.status == "OK" and result:
            api_endpoints_for_probe = result.endpoints

    # Decision gate: E7 deep-mode detection (Phase 2)
    # Only run on DYNAMIC/HYBRID e-commerce sites with --deep flag
    if (
        should_run("classifier")
        and classifier_result
        and classifier_result.type in ("DYNAMIC", "HYBRID")
        and classifier_result.ecommerce
        and classifier_result.ecommerce.is_ecommerce
        and config.deep
    ):
        logger.debug("Phase 2: E7 deep-mode detection (conditional)")
        try:
            e7_result = await _detect_deep_ecommerce(url, timeout=config.timeout, config=config)
            if e7_result:
                classifier_result.ecommerce.e7_deep_mode = e7_result
                logger.info(f"E7: Detected {e7_result.confidence} confidence, {len(e7_result.js_price_requests or [])} price requests")
        except Exception as e:
            logger.debug(f"E7 detection exception (graceful fallback): {e}")

    # Phase 2: antibot with endpoint context
    phase2_results = []
    phase2_names = []

    if should_run("antibot"):
        antibot_result = await run_module(
            "antibot",
            analyze_antibot(url, config.timeout + 15, api_endpoints=api_endpoints_for_probe),
        )
        phase2_results.append(antibot_result)
        phase2_names.append("antibot")

    names = phase1_names + phase2_names
    results = list(phase1_results) + phase2_results

    # Map results to report fields
    report_kwargs: dict = {}
    statuses: list[ModuleStatus] = []

    classifier_type = "UNKNOWN"

    for name, (result, status) in zip(names, results):
        statuses.append(status)
        if status.status == "OK":
            if name == "legal":
                report_kwargs["legal"] = result
            elif name == "classifier":
                report_kwargs["classifier"] = result
                classifier_type = result.type
            elif name == "auth_detector":
                report_kwargs["auth"] = result
            elif name == "api_detector":
                report_kwargs["api_detector"] = result
            elif name == "pagination":
                report_kwargs["pagination"] = result
            elif name == "antibot":
                report_kwargs["antibot"] = result

    # Recommender runs last — pure function
    partial_report = ReconReport(
        url=url,
        timestamp=start.isoformat(),
        scan_duration_ms=0,
        modules_status=statuses,
        **report_kwargs,
    )

    if should_run("recommender"):
        recommender_result = build_recommendation(partial_report)
        report_kwargs["recommender"] = recommender_result
        statuses.append(ModuleStatus(name="recommender", status="OK"))

    duration_ms = int((time.monotonic() - t0) * 1000)

    return ReconReport(
        url=url,
        timestamp=start.isoformat(),
        scan_duration_ms=duration_ms,
        modules_status=statuses,
        **report_kwargs,
    )


if __name__ == "__main__":
    app()
