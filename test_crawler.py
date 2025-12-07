"""
Tests for Xueqiu Crawler components.
Run with: pytest tests/ -v
"""

import asyncio
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import AppSettings, TabName, load_settings
from src.models import PostData, PostSummary, SentimentType
from src.utils import (
    clean_text,
    extract_stock_symbols,
    classify_sentiment_basic,
    identify_sectors,
    generate_content_hash,
)


class TestConfig:
    """Test configuration module."""
    
    def test_load_settings(self):
        """Test settings loading."""
        settings = load_settings()
        assert settings is not None
        assert settings.job_name is not None
        assert len(settings.available_tabs) == 8
    
    def test_tab_names(self):
        """Test all tab names are defined."""
        expected_tabs = ["热门", "7x24", "视频", "基金", "资讯", "达人", "私募", "ETF"]
        actual_tabs = [t.value for t in TabName]
        assert actual_tabs == expected_tabs
    
    def test_storage_paths(self):
        """Test storage path generation."""
        settings = load_settings()
        assert settings.get_storage_path().exists() == False  # Not created yet
        assert "raw" in str(settings.get_raw_path())
        assert "summary" in str(settings.get_summary_path())
        assert "reports" in str(settings.get_reports_path())


class TestUtils:
    """Test utility functions."""
    
    def test_clean_text(self):
        """Test text cleaning."""
        # HTML removal
        assert clean_text("<p>Hello</p>") == "Hello"
        
        # Whitespace normalization
        assert clean_text("Hello   World") == "Hello World"
        
        # Empty string
        assert clean_text("") == ""
        assert clean_text(None) == ""
    
    def test_extract_stock_symbols(self):
        """Test stock symbol extraction."""
        # Shanghai stocks
        text = "今天买了SH600519，涨停了！"
        symbols = extract_stock_symbols(text)
        assert "SH600519" in symbols or "600519" in symbols
        
        # Shenzhen stocks
        text = "SZ000001平安银行不错"
        symbols = extract_stock_symbols(text)
        assert any("000001" in s for s in symbols)
        
        # US stocks
        text = "$AAPL$ is going up!"
        symbols = extract_stock_symbols(text)
        assert "AAPL" in symbols
    
    def test_classify_sentiment_basic(self):
        """Test basic sentiment classification."""
        # Positive
        sentiment, score = classify_sentiment_basic("这只股票涨势很好，利好消息")
        assert sentiment == "positive"
        
        # Negative
        sentiment, score = classify_sentiment_basic("暴跌了，利空消息太多")
        assert sentiment == "negative"
        
        # Neutral
        sentiment, score = classify_sentiment_basic("今天市场波动不大")
        assert sentiment in ["neutral", "positive", "negative"]
    
    def test_identify_sectors(self):
        """Test sector identification."""
        # Tech sector
        sectors = identify_sectors("芯片和AI人工智能板块今天大涨")
        assert "科技" in sectors
        
        # Consumer sector
        sectors = identify_sectors("白酒消费板块继续强势")
        assert "消费" in sectors
        
        # Multiple sectors
        sectors = identify_sectors("银行股和新能源车都在涨")
        assert len(sectors) >= 2
    
    def test_generate_content_hash(self):
        """Test content hash generation."""
        hash1 = generate_content_hash("Hello World")
        hash2 = generate_content_hash("Hello World")
        hash3 = generate_content_hash("Different Content")
        
        assert hash1 == hash2  # Same content = same hash
        assert hash1 != hash3  # Different content = different hash
        assert len(hash1) == 16  # xxhash64 produces 16 char hex


class TestModels:
    """Test data models."""
    
    def test_post_data_creation(self):
        """Test PostData model."""
        post = PostData(
            id="123",
            text="Test post content",
            tab="热门",
            timestamp=datetime.utcnow()
        )
        
        assert post.id == "123"
        assert post.text == "Test post content"
        assert post.tab == "热门"
        assert post.is_valid() == True
    
    def test_post_data_validation(self):
        """Test PostData validation."""
        # Valid post
        post = PostData(id="1", text="Content", tab="热门")
        assert post.is_valid() == True
        
        # Invalid - empty text
        post = PostData(id="1", text="", tab="热门")
        assert post.is_valid() == False
        
        # Invalid - empty id
        post = PostData(id="", text="Content", tab="热门")
        assert post.is_valid() == False
    
    def test_post_data_content_hash(self):
        """Test content hash computation."""
        post1 = PostData(id="1", text="Same content", tab="热门", author="user1")
        post2 = PostData(id="2", text="Same content", tab="热门", author="user1")
        post3 = PostData(id="3", text="Different", tab="热门", author="user1")
        
        assert post1.content_hash == post2.content_hash
        assert post1.content_hash != post3.content_hash
    
    def test_post_summary_creation(self):
        """Test PostSummary model."""
        summary = PostSummary(
            post_id="123",
            post_hash="abc123",
            tab="热门",
            summary="This is a summary",
            sentiment=SentimentType.POSITIVE,
            sentiment_score=0.8
        )
        
        assert summary.post_id == "123"
        assert summary.sentiment == SentimentType.POSITIVE
        assert summary.sentiment_score == 0.8
    
    def test_sentiment_types(self):
        """Test sentiment type enum."""
        assert SentimentType.POSITIVE.value == "positive"
        assert SentimentType.NEGATIVE.value == "negative"
        assert SentimentType.NEUTRAL.value == "neutral"
        assert SentimentType.UNKNOWN.value == "unknown"


class TestCrawler:
    """Test crawler functionality (mocked)."""
    
    @pytest.fixture
    def settings(self):
        """Create test settings."""
        return load_settings()
    
    @pytest.mark.asyncio
    async def test_crawler_initialization(self, settings):
        """Test crawler can be initialized."""
        from src.crawler import XueqiuCrawler
        
        crawler = XueqiuCrawler(settings)
        assert crawler is not None
        assert crawler.settings == settings


class TestStorage:
    """Test storage functionality."""
    
    @pytest.fixture
    def settings(self):
        """Create test settings with temp directory."""
        settings = load_settings()
        settings.job_name = "test_job"
        settings.storage.base_dir = Path("/tmp/xueqiu_test")
        return settings
    
    @pytest.mark.asyncio
    async def test_storage_initialization(self, settings):
        """Test storage manager initialization."""
        from src.storage import StorageManager
        
        storage = StorageManager(settings)
        assert storage.base_path.exists()
        assert storage.raw_path.exists()
        assert storage.summary_path.exists()
        assert storage.reports_path.exists()
        
        # Cleanup
        import shutil
        shutil.rmtree(storage.base_path)


class TestLLMSummarizer:
    """Test LLM summarization (mocked)."""
    
    @pytest.fixture
    def settings(self):
        """Create test settings."""
        settings = load_settings()
        settings.llm.api_key = "test-key"
        return settings
    
    def test_fallback_summary(self, settings):
        """Test fallback summary generation."""
        from src.llm_summarizer import MockLLMSummarizer
        
        post = PostData(
            id="123",
            text="茅台涨停了！看好白酒板块",
            tab="热门",
            symbols=["SH600519"]
        )
        
        summarizer = MockLLMSummarizer(settings)
        summary = summarizer._create_fallback_summary(post)
        
        assert summary.post_id == "123"
        assert summary.sentiment in [SentimentType.POSITIVE, SentimentType.NEUTRAL, SentimentType.NEGATIVE]
        assert "SH600519" in summary.tickers


class TestReportGenerator:
    """Test report generation."""
    
    @pytest.fixture
    def settings(self):
        """Create test settings."""
        return load_settings()
    
    @pytest.fixture
    def sample_posts(self):
        """Create sample posts."""
        return [
            PostData(
                id="1",
                text="茅台涨停了！利好消息",
                tab="热门",
                symbols=["SH600519"],
                like_count=100,
                comment_count=50
            ),
            PostData(
                id="2",
                text="银行股今天表现不佳",
                tab="热门",
                symbols=["SH601398"],
                like_count=50,
                comment_count=20
            )
        ]
    
    @pytest.fixture
    def sample_summaries(self):
        """Create sample summaries."""
        return [
            PostSummary(
                post_id="1",
                post_hash="hash1",
                tab="热门",
                summary="Positive outlook on Maotai",
                tickers=["SH600519"],
                companies=["贵州茅台"],
                themes=["白酒"],
                sectors=["消费"],
                sentiment=SentimentType.POSITIVE,
                sentiment_score=0.8
            ),
            PostSummary(
                post_id="2",
                post_hash="hash2",
                tab="热门",
                summary="Banks underperforming",
                tickers=["SH601398"],
                companies=["工商银行"],
                themes=["银行"],
                sectors=["金融"],
                sentiment=SentimentType.NEGATIVE,
                sentiment_score=-0.6
            )
        ]
    
    def test_aggregate_stock_mentions(self, settings, sample_posts, sample_summaries):
        """Test stock mention aggregation."""
        from src.report_generator import ReportGenerator
        
        generator = ReportGenerator(settings)
        mentions = generator.aggregate_stock_mentions(sample_posts, sample_summaries)
        
        assert len(mentions) >= 2
        assert any(m.symbol == "SH600519" for m in mentions)
    
    def test_calculate_overall_sentiment(self, settings, sample_summaries):
        """Test overall sentiment calculation."""
        from src.report_generator import ReportGenerator
        
        generator = ReportGenerator(settings)
        sentiment = generator.calculate_overall_sentiment(sample_summaries)
        
        assert "positive" in sentiment
        assert "negative" in sentiment
        assert "neutral" in sentiment
        assert sentiment["positive"] == 1
        assert sentiment["negative"] == 1


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
