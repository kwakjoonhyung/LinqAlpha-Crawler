"""
Utility functions for Xueqiu Crawler.
Includes logging, text processing, and helper functions.
"""

import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set

import xxhash
from rich.console import Console
from rich.logging import RichHandler

from .config import SECTOR_KEYWORDS, SENTIMENT_KEYWORDS, STOCK_SYMBOL_PATTERNS


# Global console for rich output
console = Console()


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    job_name: Optional[str] = None
) -> logging.Logger:
    """
    Setup logging with rich handler and optional file output.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional path to log file
        job_name: Optional job name for logger identification
        
    Returns:
        Configured logger instance
    """
    logger_name = f"xueqiu_crawler.{job_name}" if job_name else "xueqiu_crawler"
    logger = logging.getLogger(logger_name)
    logger.setLevel(getattr(logging, level.upper()))
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Rich console handler for pretty output
    rich_handler = RichHandler(
        console=console,
        show_time=True,
        show_path=False,
        rich_tracebacks=True
    )
    rich_handler.setLevel(logging.DEBUG)
    rich_format = logging.Formatter("%(message)s")
    rich_handler.setFormatter(rich_format)
    logger.addHandler(rich_handler)
    
    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str = "xueqiu_crawler") -> logging.Logger:
    """Get or create a logger with the given name."""
    return logging.getLogger(name)


def generate_content_hash(content: str, *args) -> str:
    """
    Generate a unique hash for content deduplication.
    
    Args:
        content: Primary content to hash
        *args: Additional strings to include in hash
        
    Returns:
        Hexadecimal hash string
    """
    combined = ":".join([content] + [str(a) for a in args if a])
    return xxhash.xxh64(combined.encode('utf-8')).hexdigest()


def clean_text(text: str) -> str:
    """
    Clean and normalize text content.
    
    Args:
        text: Raw text to clean
        
    Returns:
        Cleaned text
    """
    if not text:
        return ""
    
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Remove special characters but keep Chinese and basic punctuation
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    
    return text.strip()


def extract_stock_symbols(text: str) -> List[str]:
    """
    Extract stock ticker symbols from text.
    
    Args:
        text: Text to search for symbols
        
    Returns:
        List of unique stock symbols found
    """
    symbols: Set[str] = set()
    
    for pattern in STOCK_SYMBOL_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                # Handle complex patterns with groups
                symbol = "".join(match).upper()
            else:
                symbol = match.upper()
            
            if symbol and len(symbol) >= 2:
                symbols.add(symbol)
    
    # Also look for common Chinese stock formats: $股票名称(SH600519)$ format
    cn_pattern = r'\$([^\$]+)\(([A-Z]{2}\d+)\)\$'
    cn_matches = re.findall(cn_pattern, text)
    for name, code in cn_matches:
        symbols.add(code.upper())
    
    return list(symbols)


def extract_urls(text: str) -> List[str]:
    """
    Extract URLs from text.
    
    Args:
        text: Text to search for URLs
        
    Returns:
        List of URLs found
    """
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    urls = re.findall(url_pattern, text)
    return list(set(urls))


def classify_sentiment_basic(text: str) -> tuple[str, float]:
    """
    Basic sentiment classification using keyword matching.
    
    Args:
        text: Text to classify
        
    Returns:
        Tuple of (sentiment_label, confidence_score)
    """
    text_lower = text.lower()
    
    positive_count = sum(
        1 for keyword in SENTIMENT_KEYWORDS["positive"]
        if keyword in text_lower
    )
    negative_count = sum(
        1 for keyword in SENTIMENT_KEYWORDS["negative"]
        if keyword in text_lower
    )
    neutral_count = sum(
        1 for keyword in SENTIMENT_KEYWORDS["neutral"]
        if keyword in text_lower
    )
    
    total = positive_count + negative_count + neutral_count
    
    if total == 0:
        return "neutral", 0.5
    
    if positive_count > negative_count * 1.5:
        confidence = min(0.9, 0.5 + (positive_count - negative_count) / (total * 2))
        return "positive", confidence
    elif negative_count > positive_count * 1.5:
        confidence = min(0.9, 0.5 + (negative_count - positive_count) / (total * 2))
        return "negative", confidence
    else:
        return "neutral", 0.5


def identify_sectors(text: str) -> List[str]:
    """
    Identify market sectors mentioned in text.
    
    Args:
        text: Text to analyze
        
    Returns:
        List of sector names found
    """
    sectors = []
    
    for sector, keywords in SECTOR_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                if sector not in sectors:
                    sectors.append(sector)
                break
    
    return sectors


def truncate_text(text: str, max_length: int = 200, suffix: str = "...") -> str:
    """
    Truncate text to specified length.
    
    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated
        
    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def format_timestamp(dt: Optional[datetime] = None, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Format datetime to string.
    
    Args:
        dt: Datetime to format (defaults to now)
        fmt: Format string
        
    Returns:
        Formatted datetime string
    """
    if dt is None:
        dt = datetime.now()
    return dt.strftime(fmt)


def parse_timestamp(timestamp: any) -> Optional[datetime]:
    """
    Parse various timestamp formats to datetime.
    
    Args:
        timestamp: Timestamp in various formats (int ms, string, etc.)
        
    Returns:
        Parsed datetime or None
    """
    if timestamp is None:
        return None
    
    try:
        if isinstance(timestamp, datetime):
            return timestamp
        elif isinstance(timestamp, (int, float)):
            # Assume milliseconds if > year 2100 in seconds
            if timestamp > 4102444800:
                timestamp = timestamp / 1000
            return datetime.fromtimestamp(timestamp)
        elif isinstance(timestamp, str):
            # Try various formats
            formats = [
                "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
            ]
            for fmt in formats:
                try:
                    return datetime.strptime(timestamp, fmt)
                except ValueError:
                    continue
    except Exception:
        pass
    
    return None


def ensure_directory(path: Path) -> Path:
    """
    Ensure directory exists, create if necessary.
    
    Args:
        path: Directory path
        
    Returns:
        The path (created if necessary)
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_filename(name: str, max_length: int = 100) -> str:
    """
    Convert string to safe filename.
    
    Args:
        name: Original name
        max_length: Maximum filename length
        
    Returns:
        Safe filename string
    """
    # Replace unsafe characters
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    # Remove leading/trailing whitespace and dots
    safe = safe.strip(' .')
    # Truncate if necessary
    if len(safe) > max_length:
        safe = safe[:max_length]
    return safe or "unnamed"


def calculate_progress(current: int, total: int) -> float:
    """
    Calculate progress percentage.
    
    Args:
        current: Current progress
        total: Total items
        
    Returns:
        Progress percentage (0-100)
    """
    if total <= 0:
        return 0.0
    return min(100.0, (current / total) * 100)


class RateLimiter:
    """Simple rate limiter for API calls."""
    
    def __init__(self, calls_per_second: float = 1.0):
        """
        Initialize rate limiter.
        
        Args:
            calls_per_second: Maximum calls per second
        """
        self.min_interval = 1.0 / calls_per_second
        self.last_call = 0.0
    
    async def wait(self):
        """Wait if necessary to respect rate limit."""
        import asyncio
        import time
        
        elapsed = time.time() - self.last_call
        if elapsed < self.min_interval:
            await asyncio.sleep(self.min_interval - elapsed)
        self.last_call = time.time()


def format_number(n: int) -> str:
    """
    Format number with thousands separators.
    
    Args:
        n: Number to format
        
    Returns:
        Formatted string
    """
    return f"{n:,}"


def get_sentiment_emoji(sentiment: str) -> str:
    """
    Get emoji for sentiment type.
    
    Args:
        sentiment: Sentiment type
        
    Returns:
        Corresponding emoji
    """
    mapping = {
        "positive": "📈",
        "negative": "📉",
        "neutral": "➡️",
        "unknown": "❓"
    }
    return mapping.get(sentiment.lower(), "❓")