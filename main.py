"""
main.py
CLI entry point for scraping_recon. Built with Typer.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from typing import Optional

import typer
from rich.console import Console

from config import Config
from models.schemas import ModuleStatus, ReconReport
from modules.antibot import analyze_antibot
from modules.api_detector import detect_apis
from modules.auth_detector import detect_auth
from modules.classifier import classify_page
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

    # Run modules concurrently
    tasks = []
    names = []

    if should_run("legal"):
        tasks.append(run_module("legal", analyze_legal(url, config.timeout)))
        names.append("legal")
    if should_run("classifier"):
        tasks.append(run_module("classifier", classify_page(url, config.timeout)))
        names.append("classifier")
    if should_run("auth_detector"):
        tasks.append(run_module("auth_detector", detect_auth(url, config.timeout)))
        names.append("auth_detector")
    if should_run("api_detector"):
        tasks.append(run_module("api_detector", detect_apis(url, config.timeout)))
        names.append("api_detector")
    if should_run("pagination"):
        tasks.append(run_module("pagination", detect_pagination(url, config.timeout)))
        names.append("pagination")
    if should_run("antibot"):
        tasks.append(run_module("antibot", analyze_antibot(url, config.timeout + 15)))
        names.append("antibot")

    results = await asyncio.gather(*tasks)

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
