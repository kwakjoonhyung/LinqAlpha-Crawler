#!/usr/bin/env python3
"""
Xueqiu Investor Discussion Crawler - Main Entry Point

This module provides the CLI interface and orchestrates the complete
data-to-insight pipeline:
1. Crawls Xueqiu investor discussions
2. Cleans and structures raw posts
3. Generates LLM-based summaries
4. Produces final market sentiment report

Usage:
    python main.py --tabs all              # Crawl all tabs
    python main.py --tabs 热门 7x24         # Crawl specific tabs
    python main.py --max-posts 50          # Limit posts per tab
    python main.py --no-llm                # Skip LLM summarization
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import AppSettings, TabName, load_settings
from src.crawler import XueqiuCrawler
from src.llm_summarizer import LLMSummarizer, MockLLMSummarizer
from src.models import PostData, PostSummary, TabStatistics
from src.report_generator import ReportGenerator
from src.storage import StorageManager, IncrementalSaver
from src.utils import setup_logging, get_logger

# CLI app
app = typer.Typer(
    name="xueqiu-crawler",
    help="Xueqiu Investor Discussion Crawler and Report Generator",
    add_completion=False
)

# Console for rich output
console = Console()


def parse_tabs(tabs: List[str]) -> List[TabName]:
    """
    Parse tab names from CLI arguments.
    
    Args:
        tabs: List of tab names or ['all']
        
    Returns:
        List of TabName enums
    """
    if not tabs or "all" in [t.lower() for t in tabs]:
        return list(TabName)
    
    parsed = []
    tab_mapping = {t.value: t for t in TabName}
    
    for tab in tabs:
        if tab in tab_mapping:
            parsed.append(tab_mapping[tab])
        else:
            console.print(f"[yellow]Warning: Unknown tab '{tab}'[/yellow]")
    
    return parsed or list(TabName)


async def run_crawler(
    settings: AppSettings,
    tabs: List[TabName],
    max_posts: int,
    use_llm: bool,
    storage: StorageManager,
    saver: IncrementalSaver
) -> dict:
    """
    Run the complete crawling pipeline.
    
    Args:
        settings: Application settings
        tabs: Tabs to crawl
        max_posts: Max posts per tab
        use_llm: Whether to use LLM summarization
        storage: Storage manager
        saver: Incremental saver
        
    Returns:
        Dictionary with results
    """
    logger = get_logger("main")
    results = {
        "posts_by_tab": {},
        "summaries_by_tab": {},
        "tab_stats": {},
        "errors": []
    }
    
    # Start incremental saver
    await saver.start()
    
    try:
        # Phase 1: Crawling
        console.print(Panel("[bold blue]Phase 1: Crawling Xueqiu Discussions[/bold blue]"))
        
        async with XueqiuCrawler(settings) as crawler:
            # Set callback for incremental saving
            async def save_callback(tab: str, posts: List[PostData]):
                await saver.add_posts(tab, posts)
            
            crawler.set_post_callback(save_callback)
            
            # Crawl tabs with progress bar
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                console=console
            ) as progress:
                task = progress.add_task(
                    f"Crawling {len(tabs)} tabs...",
                    total=len(tabs)
                )
                
                results["posts_by_tab"] = await crawler.crawl_tabs(tabs, max_posts)
                results["tab_stats"] = crawler.get_statistics()
                
                progress.update(task, completed=len(tabs))
        
        # Save final posts
        for tab, posts in results["posts_by_tab"].items():
            await storage.save_posts(tab, posts, incremental=True)
        
        # Display crawl summary
        total_posts = sum(len(posts) for posts in results["posts_by_tab"].values())
        console.print(f"✅ Collected [green]{total_posts}[/green] posts from {len(results['posts_by_tab'])} tabs")
        
        # Phase 2: LLM Summarization
        if use_llm and settings.llm.api_key:
            console.print(Panel("[bold blue]Phase 2: LLM Summarization[/bold blue]"))
            
            async with LLMSummarizer(settings) as summarizer:
                for tab, posts in results["posts_by_tab"].items():
                    summaries = await summarizer.summarize_posts(posts)
                    results["summaries_by_tab"][tab] = summaries
                    await storage.save_summaries(tab, summaries, incremental=True)
                
                stats = summarizer.get_statistics()
                console.print(
                    f"✅ Generated [green]{stats['successful_requests']}[/green] summaries "
                    f"({stats['failed_requests']} failures)"
                )
        else:
            console.print("[yellow]⚠️ Using fallback summarization (no LLM API key)[/yellow]")
            
            async with MockLLMSummarizer(settings) as summarizer:
                for tab, posts in results["posts_by_tab"].items():
                    summaries = await summarizer.summarize_posts(posts)
                    results["summaries_by_tab"][tab] = summaries
                    await storage.save_summaries(tab, summaries, incremental=True)
        
        # Phase 3: Report Generation
        console.print(Panel("[bold blue]Phase 3: Report Generation[/bold blue]"))
        
        generator = ReportGenerator(settings)
        report, markdown = await generator.generate_and_save(
            results["posts_by_tab"],
            results["summaries_by_tab"],
            results["tab_stats"],
            storage
        )
        
        # Use storage.reports_path (attribute, not method)
        console.print(
            f"✅ Report generated: [green]{storage.reports_path / settings.storage.report_filename}[/green]"
        )
        
    except Exception as e:
        logger.error(f"Pipeline error: {e}")
        results["errors"].append(str(e))
        raise
    
    finally:
        # Stop incremental saver
        await saver.stop()
    
    return results


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    tabs: List[str] = typer.Option(
        ["all"],
        "--tabs", "-t",
        help="Tabs to crawl (热门, 7x24, 视频, 基金, 资讯, 达人, 私募, ETF) or 'all'"
    ),
    max_posts: int = typer.Option(
        50,
        "--max-posts", "-m",
        help="Maximum posts to collect per tab"
    ),
    job_name: Optional[str] = typer.Option(
        None,
        "--job-name", "-j",
        help="Custom job name (default: run_YYYYMMDD_HHMMSS)"
    ),
    output_dir: Path = typer.Option(
        Path("storage"),
        "--output", "-o",
        help="Output directory for data storage"
    ),
    llm_api_key: Optional[str] = typer.Option(
        None,
        "--api-key", "-k",
        envvar="FIREWORKS_API_KEY",
        help="Fireworks API key for LLM summarization"
    ),
    no_llm: bool = typer.Option(
        False,
        "--no-llm",
        help="Skip LLM summarization (use basic analysis)"
    ),
    log_level: str = typer.Option(
        "INFO",
        "--log-level", "-l",
        help="Logging level (DEBUG, INFO, WARNING, ERROR)"
    ),
    concurrent_tabs: int = typer.Option(
        4,
        "--concurrent", "-c",
        help="Number of tabs to crawl concurrently"
    )
):
    """
    Xueqiu Investor Discussion Crawler and Report Generator
    
    Crawls investor discussions from Xueqiu (雪球) and generates
    structured sentiment reports for hedge fund analysts.
    
    Cookie Setup (Recommended for better results):
        Set XUEQIU_COOKIE environment variable with your cookie.
        
    Playwright Requirement:
        This crawler requires Playwright. Install with:
        pip install playwright && playwright install chromium
    """
    # If a subcommand is invoked, skip the main logic
    if ctx.invoked_subcommand is not None:
        return
    
    # Display banner
    console.print(Panel.fit(
        "[bold cyan]Xueqiu Investor Discussion Crawler[/bold cyan]\n"
        "AI & Alt Data Team - Linq 2025",
        border_style="cyan"
    ))
    
    # Check environment
    cookie_status = "Set ✓" if os.environ.get("XUEQIU_COOKIE") else "Not set"
    
    # Load settings
    settings = load_settings()
    
    # Override settings from CLI
    if job_name:
        settings.job_name = job_name
    settings.storage.base_dir = output_dir
    settings.log_level = log_level
    settings.crawler.max_posts_per_tab = max_posts
    settings.crawler.max_concurrent_tabs = concurrent_tabs
    
    if llm_api_key:
        settings.llm.api_key = llm_api_key
    
    # Setup logging
    setup_logging(level=log_level, job_name=settings.job_name)
    logger = get_logger("main")
    
    # Parse tabs
    parsed_tabs = parse_tabs(tabs)
    
    # Check Playwright availability
    try:
        import playwright
        playwright_status = "Available ✓"
    except ImportError:
        playwright_status = "Not installed ✗"
        console.print("[red]Error: Playwright is required but not installed.[/red]")
        console.print("Run: [cyan]pip install playwright && playwright install chromium[/cyan]")
        sys.exit(1)
    
    # Display configuration
    config_table = Table(title="Configuration", show_header=False)
    config_table.add_column("Setting", style="cyan")
    config_table.add_column("Value", style="green")
    config_table.add_row("Job Name", settings.job_name)
    config_table.add_row("Output Directory", str(settings.get_storage_path()))
    config_table.add_row("Tabs", ", ".join(t.value for t in parsed_tabs))
    config_table.add_row("Max Posts/Tab", str(max_posts))
    config_table.add_row("Concurrent Tabs", str(concurrent_tabs))
    config_table.add_row("LLM Enabled", "No" if no_llm else ("Yes" if settings.llm.api_key else "Fallback"))
    config_table.add_row("Cookie", cookie_status)
    config_table.add_row("Playwright", playwright_status)
    console.print(config_table)
    console.print()
    
    # Initialize storage
    storage = StorageManager(settings)
    saver = IncrementalSaver(storage, settings.storage.save_interval)
    
    # Run pipeline
    start_time = datetime.now()
    
    try:
        results = asyncio.run(run_crawler(
            settings=settings,
            tabs=parsed_tabs,
            max_posts=max_posts,
            use_llm=not no_llm,
            storage=storage,
            saver=saver
        ))
        
        # Display final summary
        duration = (datetime.now() - start_time).total_seconds()
        total_posts = sum(len(posts) for posts in results["posts_by_tab"].values())
        total_summaries = sum(len(s) for s in results["summaries_by_tab"].values())
        
        summary_table = Table(title="Crawl Summary")
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green")
        summary_table.add_row("Total Posts", str(total_posts))
        summary_table.add_row("Total Summaries", str(total_summaries))
        summary_table.add_row("Tabs Crawled", str(len(results["posts_by_tab"])))
        summary_table.add_row("Duration", f"{duration:.1f} seconds")
        summary_table.add_row("Errors", str(len(results["errors"])))
        
        console.print()
        console.print(summary_table)
        console.print()
        
        # Display output paths
        console.print(Panel(
            f"[bold green]✅ Pipeline Complete![/bold green]\n\n"
            f"Raw Data: {settings.get_raw_path()}\n"
            f"Summaries: {settings.get_summary_path()}\n"
            f"Report: {settings.get_reports_path() / settings.storage.report_filename}",
            title="Output Files",
            border_style="green"
        ))
        
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️ Interrupted by user[/yellow]")
        sys.exit(1)
    
    except Exception as e:
        console.print(f"\n[red]❌ Error: {e}[/red]")
        logger.exception("Pipeline failed")
        sys.exit(1)


@app.command()
def list_tabs():
    """List all available tabs for crawling."""
    table = Table(title="Available Tabs")
    table.add_column("Tab Name", style="cyan")
    table.add_column("Description", style="green")
    
    descriptions = {
        "热门": "Hot/Trending Discussions",
        "7x24": "24/7 Live News & Updates",
        "视频": "Video Content",
        "基金": "Mutual Funds Discussions",
        "资讯": "News & Information",
        "达人": "Expert/Influencer Posts",
        "私募": "Private Equity Discussions",
        "ETF": "ETF Discussions"
    }
    
    for tab in TabName:
        table.add_row(tab.value, descriptions.get(tab.value, ""))
    
    console.print(table)


@app.command()
def version():
    """Show version information."""
    from src import __version__
    console.print(f"Xueqiu Crawler v{__version__}")


if __name__ == "__main__":
    app()