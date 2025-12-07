"""
Xueqiu Investor Discussion Crawler

A Python-based crawler that captures investor discussions from Xueqiu
and generates structured sentiment reports for hedge fund analysts.
"""

__version__ = "1.0.0"
__author__ = "AI & Alt Data Team"

from .config import (
    AppSettings,
    CrawlerSettings,
    LLMSettings,
    StorageSettings,
    TabName,
    load_settings,
)
from .models import (
    CrawlReport,
    PostData,
    PostSummary,
    SentimentType,
    StockMention,
    TabStatistics,
    ThemeAnalysis,
)
from .crawler import XueqiuCrawler
from .llm_summarizer import LLMSummarizer, BatchSummarizer, MockLLMSummarizer
from .report_generator import ReportGenerator
from .storage import StorageManager, IncrementalSaver

__all__ = [
    # Settings
    "AppSettings",
    "CrawlerSettings", 
    "LLMSettings",
    "StorageSettings",
    "TabName",
    "load_settings",
    # Models
    "CrawlReport",
    "PostData",
    "PostSummary",
    "SentimentType",
    "StockMention",
    "TabStatistics",
    "ThemeAnalysis",
    # Crawler
    "XueqiuCrawler",
    # LLM
    "LLMSummarizer",
    "BatchSummarizer",
    "MockLLMSummarizer",
    # Report
    "ReportGenerator",
    # Storage
    "StorageManager",
    "IncrementalSaver",
]