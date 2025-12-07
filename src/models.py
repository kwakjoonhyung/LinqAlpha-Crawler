"""
Data models for Xueqiu Crawler.
Defines the structure of posts, summaries, and reports.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import xxhash
from pydantic import BaseModel, ConfigDict, Field, computed_field


class SentimentType(str, Enum):
    """Sentiment classification types."""
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    UNKNOWN = "unknown"


class PostData(BaseModel):
    """Raw post data extracted from Xueqiu."""
    
    # Required fields
    id: str = Field(..., description="Unique post identifier")
    text: str = Field(..., description="Post body text (cleaned)")
    html: str = Field(default="", description="Raw article HTML")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Collection time (ISO format)"
    )
    tab: str = Field(..., description="Source tab name")
    
    # Optional fields
    author: Optional[str] = Field(default=None, description="Author username")
    author_id: Optional[str] = Field(default=None, description="Author user ID")
    author_avatar: Optional[str] = Field(default=None, description="Author avatar URL")
    author_verified: bool = Field(default=False, description="Is author verified")
    
    # Engagement metrics
    like_count: int = Field(default=0, ge=0)
    comment_count: int = Field(default=0, ge=0)
    retweet_count: int = Field(default=0, ge=0)
    view_count: int = Field(default=0, ge=0)
    
    # Extracted data
    symbols: List[str] = Field(default_factory=list, description="Detected stock tickers")
    urls: List[str] = Field(default_factory=list, description="URLs in post")
    images: List[str] = Field(default_factory=list, description="Image URLs")
    
    # Metadata
    post_url: Optional[str] = Field(default=None, description="Original post URL")
    created_at: Optional[datetime] = Field(default=None, description="Post creation time")
    source: Optional[str] = Field(default=None, description="Post source/client")
    
    # Additional raw data
    raw_data: Dict[str, Any] = Field(default_factory=dict, description="Additional raw fields")
    
    @computed_field
    @property
    def content_hash(self) -> str:
        """Generate content hash for deduplication."""
        content = f"{self.text}:{self.author or ''}:{self.tab}"
        return xxhash.xxh64(content.encode()).hexdigest()
    
    def is_valid(self) -> bool:
        """Check if post data is valid and complete."""
        return bool(
            self.id and 
            self.text and 
            len(self.text.strip()) > 0 and
            self.tab
        )
    
    model_config = ConfigDict(
        ser_json_timedelta='iso8601'
    )


class PostSummary(BaseModel):
    """LLM-generated summary for a post."""
    
    post_id: str = Field(..., description="Reference to original post ID")
    post_hash: str = Field(..., description="Content hash of original post")
    tab: str = Field(..., description="Source tab name")
    
    # Summary content
    summary: str = Field(..., description="Brief summary of the post")
    key_points: List[str] = Field(default_factory=list, description="Key discussion points")
    
    # Extracted entities
    tickers: List[str] = Field(default_factory=list, description="Stock tickers mentioned")
    companies: List[str] = Field(default_factory=list, description="Company names mentioned")
    themes: List[str] = Field(default_factory=list, description="Investment themes")
    sectors: List[str] = Field(default_factory=list, description="Market sectors")
    
    # Sentiment analysis
    sentiment: SentimentType = Field(default=SentimentType.UNKNOWN)
    sentiment_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    sentiment_reasoning: Optional[str] = Field(default=None)
    
    # Metadata
    processed_at: datetime = Field(default_factory=datetime.utcnow)
    model_used: str = Field(default="")
    processing_time_ms: int = Field(default=0, ge=0)
    
    # Original text reference (truncated)
    original_text_preview: str = Field(default="", max_length=200)
    
    model_config = ConfigDict(
        ser_json_timedelta='iso8601'
    )


class StockMention(BaseModel):
    """Aggregated stock mention data."""
    
    symbol: str = Field(..., description="Stock ticker symbol")
    name: Optional[str] = Field(default=None, description="Company name")
    mention_count: int = Field(default=0, ge=0)
    
    # Sentiment breakdown
    positive_mentions: int = Field(default=0, ge=0)
    neutral_mentions: int = Field(default=0, ge=0)
    negative_mentions: int = Field(default=0, ge=0)
    
    # Sample posts
    sample_post_ids: List[str] = Field(default_factory=list)
    
    # Calculated sentiment
    @computed_field
    @property
    def overall_sentiment(self) -> SentimentType:
        """Calculate overall sentiment based on mentions."""
        if self.positive_mentions > self.negative_mentions * 1.5:
            return SentimentType.POSITIVE
        elif self.negative_mentions > self.positive_mentions * 1.5:
            return SentimentType.NEGATIVE
        return SentimentType.NEUTRAL
    
    @computed_field
    @property
    def sentiment_ratio(self) -> float:
        """Calculate positive to negative sentiment ratio."""
        total = self.positive_mentions + self.negative_mentions
        if total == 0:
            return 0.5
        return self.positive_mentions / total


class ThemeAnalysis(BaseModel):
    """Aggregated theme/sector analysis."""
    
    theme: str = Field(..., description="Theme or sector name")
    mention_count: int = Field(default=0, ge=0)
    related_stocks: List[str] = Field(default_factory=list)
    
    # Sentiment
    sentiment_distribution: Dict[str, int] = Field(
        default_factory=lambda: {"positive": 0, "neutral": 0, "negative": 0}
    )
    
    # Representative quotes
    representative_quotes: List[str] = Field(default_factory=list, max_length=5)
    
    # Trend indicator
    trend_direction: Optional[str] = Field(default=None)  # "up", "down", "stable"


class TabStatistics(BaseModel):
    """Statistics for a single tab."""
    
    tab_name: str
    total_posts: int = Field(default=0, ge=0)
    valid_posts: int = Field(default=0, ge=0)
    duplicate_posts: int = Field(default=0, ge=0)
    
    # Sentiment distribution
    positive_posts: int = Field(default=0, ge=0)
    neutral_posts: int = Field(default=0, ge=0)
    negative_posts: int = Field(default=0, ge=0)
    
    # Top mentions
    top_stocks: List[str] = Field(default_factory=list)
    top_themes: List[str] = Field(default_factory=list)
    
    # Time range
    earliest_post: Optional[datetime] = None
    latest_post: Optional[datetime] = None
    
    # Crawl metadata
    crawl_duration_seconds: float = Field(default=0.0, ge=0)
    errors_count: int = Field(default=0, ge=0)


class CrawlReport(BaseModel):
    """Complete crawl job report."""
    
    # Job identification
    job_name: str
    job_start: datetime
    job_end: Optional[datetime] = None
    
    # Overall statistics
    total_posts_collected: int = Field(default=0, ge=0)
    total_unique_posts: int = Field(default=0, ge=0)
    total_posts_summarized: int = Field(default=0, ge=0)
    
    # Tab-level statistics
    tab_statistics: Dict[str, TabStatistics] = Field(default_factory=dict)
    
    # Aggregated analysis
    stock_mentions: List[StockMention] = Field(default_factory=list)
    theme_analysis: List[ThemeAnalysis] = Field(default_factory=list)
    
    # Overall sentiment
    overall_sentiment: Dict[str, int] = Field(
        default_factory=lambda: {"positive": 0, "neutral": 0, "negative": 0}
    )
    
    # Representative discussions
    top_discussions: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Errors and warnings
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    
    model_config = ConfigDict(
        ser_json_timedelta='iso8601'
    )
