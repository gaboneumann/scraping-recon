"""
report/terminal.py
Renders a ReconReport to the terminal using Rich panels and tables.
"""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table
from rich.text import Text

from models.schemas import ReconReport

RISK_COLORS = {"LOW": "green", "MEDIUM": "yellow", "HIGH": "red", "UNKNOWN": "dim", "NONE": "green"}
LEVEL_COLORS = {"NONE": "green", "LOW": "green", "MEDIUM": "yellow", "HIGH": "red", "EXTREME": "bold red"}
STATUS_COLORS = {"OK": "green", "INCOMPLETE": "yellow", "BLOCKED": "red", "SKIPPED": "dim"}


def render(report: ReconReport, console: Console | None = None) -> None:
    """Render the full ReconReport to the terminal."""
    if console is None:
        console = Console()

    _render_header(console, report)

    if report.legal:
        _render_legal(console, report.legal)
    if report.classifier:
        _render_classifier(console, report.classifier)
    if report.auth:
        _render_auth(console, report.auth)
    if report.api_detector:
        _render_api(console, report.api_detector)
    if report.pagination:
        _render_pagination(console, report.pagination)
    if report.antibot:
        show_warning = (
            report.classifier is not None
            and report.classifier.type in ("DYNAMIC", "API_DRIVEN")
            and report.antibot.overall_score < 5.0
        )
        _render_antibot(console, report.antibot, show_warning)
    if report.recommender:
        _render_recommender(console, report.recommender)

    _render_footer(console, report)


# ── Sections ──────────────────────────────────────────────────────

def _render_header(console: Console, report: ReconReport) -> None:
    content = (
        f"[bold]URL:[/bold] {report.url}\n"
        f"[bold]Timestamp:[/bold] {report.timestamp}\n"
        f"[bold]Duration:[/bold] {report.scan_duration_ms}ms"
    )
    console.print(Panel(content, title="[bold blue]scraping_recon[/bold blue]", expand=False))


def _render_legal(console: Console, legal) -> None:
    table = Table(show_header=True, header_style="bold")
    table.add_column("Check")
    table.add_column("Result")
    table.add_column("Detail")

    r = legal.robots_txt
    table.add_row(
        "robots.txt",
        "[green]found[/green]" if r.found else "[dim]not found[/dim]",
        f"path allowed: {r.target_path_allowed} | ua_specific: {r.ua_specific}"
        + (f" | delay: {r.crawl_delay_seconds}s" if r.crawl_delay_seconds else ""),
    )

    s = legal.sitemap
    table.add_row(
        "Sitemap",
        "[green]found[/green]" if s.found else "[dim]not found[/dim]",
        f"type: {s.type} | urls: {s.url_count}" if s.found else "—",
    )

    t = legal.tos
    risk_color = RISK_COLORS.get(t.risk_level, "white")
    table.add_row(
        "Terms of Service",
        "[green]found[/green]" if t.found else "[dim]not found[/dim]",
        f"[{risk_color}]risk: {t.risk_level}[/{risk_color}]"
        + (f" | keywords: {', '.join(t.flagged_keywords)}" if t.flagged_keywords else ""),
    )

    console.print(Panel(table, title="[bold]Legal Scope[/bold]"))


def _render_classifier(console: Console, c) -> None:
    table = Table(show_header=False, box=None)
    table.add_column("Key", style="bold")
    table.add_column("Value")

    table.add_row("Type", f"[bold cyan]{c.type}[/bold cyan] ({c.confidence} confidence)")
    table.add_row("Frameworks", ", ".join(c.js_frameworks) if c.js_frameworks else "none")
    table.add_row("CMS", c.cms or "none")
    table.add_row("Server", c.server or "unknown")
    table.add_row("CDN", c.cdn or "none")
    table.add_row("Locales", ", ".join(c.locales) if c.locales else "none detected")
    table.add_row("Mobile differs", "[yellow]yes[/yellow]" if c.mobile_differs else "no")
    table.add_row("Content ratio", f"{c.content_ratio:.3f}")
    table.add_row("Response time", f"{c.response_time_ms}ms")
    table.add_row("Internal links", f"{c.internal_link_count} (~{c.estimated_pages} pages)")

    sd = c.structured_data
    sd_text = ", ".join(sd.schema_types) if sd.schema_types else "none"
    if sd.scraping_shortcut:
        sd_text = f"[green]{sd_text} ✓ shortcut[/green]"
    table.add_row("Structured data", sd_text)

    sh = c.security_headers
    sh_parts = []
    if sh.csp:
        sh_parts.append(f"CSP{'(strict)' if sh.csp_blocks_inline else ''}")
    if sh.hsts:
        sh_parts.append("HSTS")
    if sh.x_frame_options:
        sh_parts.append("X-Frame-Options")
    table.add_row("Security headers", ", ".join(sh_parts) if sh_parts else "none")

    if c.cache_control:
        table.add_row("Cache-Control", c.cache_control)
    if c.last_modified:
        table.add_row("Last-Modified", c.last_modified)

    console.print(Panel(table, title="[bold]Page Classification[/bold]"))


def _render_auth(console: Console, auth) -> None:
    if not auth.required and not auth.cookie_consent_blocking:
        console.print(Panel("[green]No authentication required[/green]", title="[bold]Auth & Access[/bold]"))
        return

    table = Table(show_header=False, box=None)
    table.add_column("Key", style="bold")
    table.add_column("Value")

    color = "yellow" if auth.required else "green"
    table.add_row("Required", f"[{color}]{auth.required}[/{color}]")
    table.add_row("Type", auth.type)
    if auth.login_url:
        table.add_row("Login URL", auth.login_url)
    if auth.paywall_type and auth.paywall_type != "NONE":
        pw_color = "red" if auth.paywall_type == "HARD" else "yellow"
        table.add_row("Paywall", f"[{pw_color}]{auth.paywall_type}[/{pw_color}]")
    table.add_row(
        "Cookie consent",
        "[yellow]blocking[/yellow]" if auth.cookie_consent_blocking else "not detected",
    )

    console.print(Panel(table, title="[bold]Auth & Access[/bold]"))


def _render_api(console: Console, api) -> None:
    if not api.internal_api_found and not api.endpoints_may_be_incomplete:
        console.print(Panel("[dim]No internal APIs detected[/dim]", title="[bold]API Endpoints[/bold]"))
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Type")
    table.add_column("URL")
    table.add_column("Auth")

    for ep in api.endpoints:
        table.add_row(
            ep.type,
            ep.url[:70],
            "?" if ep.authenticated is None else str(ep.authenticated),
        )

    content = table if api.endpoints else Text("No endpoints found in static HTML", style="dim")

    extra = ""
    if api.state_blobs_found:
        extra += f"\nState blobs: {', '.join(api.state_blobs_found)}"
    if api.endpoints_may_be_incomplete:
        extra += "\n[yellow]⚠ Endpoints may be incomplete — site is DYNAMIC[/yellow]"
    if api.recommendation:
        extra += f"\n{api.recommendation}"

    console.print(Panel(
        Text.assemble(content if isinstance(content, Text) else "") if isinstance(content, Text)
        else content,
        title="[bold]API Endpoints[/bold]",
    ))
    if extra:
        console.print(extra.strip())


def _render_pagination(console: Console, p) -> None:
    color = "yellow" if p.requires_js else "green"
    detail = f"parameter: {p.parameter}" if p.parameter else ""
    if p.example_next_url:
        detail += f" | next: {p.example_next_url[:60]}"
    content = (
        f"[bold]Type:[/bold] [{color}]{p.type}[/{color}]\n"
        f"[bold]Requires JS:[/bold] {p.requires_js}"
        + (f"\n{detail}" if detail else "")
    )
    console.print(Panel(content, title="[bold]Pagination[/bold]"))


def _render_antibot(console: Console, ab, show_underestimation_warning: bool = False) -> None:
    level_color = LEVEL_COLORS.get(ab.overall_level, "white")

    # Score progress bar
    progress = Progress(
        TextColumn("[bold]Anti-Bot Score:[/bold]"),
        BarColumn(bar_width=30),
        TextColumn(f"[{level_color}]{ab.overall_score}/10 ({ab.overall_level})[/{level_color}]"),
        expand=False,
    )
    task = progress.add_task("", total=10, completed=ab.overall_score)

    table = Table(show_header=True, header_style="bold")
    table.add_column("Dimension")
    table.add_column("Score", justify="center")
    table.add_column("Detail")

    dims = ab.dimensions.model_dump()
    details = {
        "waf":                  f"vendor: {ab.dimensions.waf.vendor or 'none'}",
        "tls_fingerprint":      f"sensitivity: {ab.dimensions.tls_fingerprint.sensitivity}",
        "rate_limiting":        f"triggered_at: {ab.dimensions.rate_limiting.triggered_at}",
        "captcha":              f"provider: {ab.dimensions.captcha.provider or 'none'}",
        "browser_fingerprinting": f"libraries: {', '.join(ab.dimensions.browser_fingerprinting.libraries) or 'none'}",
        "honeypots":            f"count: {ab.dimensions.honeypots.count}",
        "ip_reputation":        f"geo_block: {ab.dimensions.ip_reputation.geo_block}",
    }

    for dim, val in dims.items():
        score = val["score"]
        color = "green" if score == 0 else "yellow" if score <= 2 else "red"
        table.add_row(dim.replace("_", " ").title(), f"[{color}]{score}[/{color}]", details.get(dim, ""))

    console.print(Panel(progress, title="[bold]Anti-Bot Protection[/bold]"))
    if show_underestimation_warning:
        console.print(Panel(
            "[yellow]⚠ Score may be underestimated[/yellow] — dynamic site: "
            "runtime protections (fingerprinting, CAPTCHA, rate-limits) are not visible statically. "
            "Run with [bold]--deep[/bold] for full assessment.",
            border_style="yellow",
            padding=(0, 1),
        ))
    console.print(table)


def _render_recommender(console: Console, rec) -> None:
    table = Table(show_header=False, box=None)
    table.add_column("Key", style="bold")
    table.add_column("Value")

    table.add_row("Primary", f"[bold green]{rec.primary_library}[/bold green]")
    if rec.secondary_library:
        table.add_row("Fallback", rec.secondary_library)
    if rec.managed_api_suggested:
        table.add_row("Managed APIs", ", ".join(rec.managed_api_options))
    table.add_row("Complexity", f"{rec.estimated_complexity}/10")
    table.add_row("Est. dev time", rec.estimated_dev_time)

    if rec.additional_flags:
        flags_text = "\n".join(f"  • {f}" for f in rec.additional_flags)
        table.add_row("Flags", flags_text)

    table.add_row("Summary", rec.full_stack_recommendation)

    console.print(Panel(table, title="[bold]Recommendations[/bold]"))


def _render_footer(console: Console, report: ReconReport) -> None:
    total = len(report.modules_status)
    ok = sum(1 for m in report.modules_status if m.status == "OK")
    failures = [m.name for m in report.modules_status if m.status not in ("OK", "SKIPPED")]

    color = "green" if not failures else "yellow"
    failure_str = f" | Partial failures: {', '.join(failures)}" if failures else ""
    console.print(
        f"[{color}]Modules completed: {ok}/{total}{failure_str}[/{color}]"
    )
