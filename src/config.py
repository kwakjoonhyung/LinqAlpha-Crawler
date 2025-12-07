"""
Configuration module for Xueqiu Crawler.
Handles all settings, constants, and environment variables.
"""

import os
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional

from pydantic import ConfigDict, Field
from pydantic_settings import BaseSettings


class TabName(str, Enum):
    """Available tabs on Xueqiu homepage."""
    REMEN = "热门"       # Hot/Popular
    QIXERSHISI = "7x24"  # 24/7 News
    SHIPIN = "视频"      # Video
    JIJIN = "基金"       # Funds
    ZIXUN = "资讯"       # Information/News
    DAREN = "达人"       # Influencers/Experts
    SIMU = "私募"        # Private Equity
    ETF = "ETF"          # ETF


# Tab URL mappings for Xueqiu
TAB_URL_MAPPING = {
    TabName.REMEN: "https://xueqiu.com/",
    TabName.QIXERSHISI: "https://xueqiu.com/",
    TabName.SHIPIN: "https://xueqiu.com/",
    TabName.JIJIN: "https://xueqiu.com/",
    TabName.ZIXUN: "https://xueqiu.com/",
    TabName.DAREN: "https://xueqiu.com/",
    TabName.SIMU: "https://xueqiu.com/",
    TabName.ETF: "https://xueqiu.com/",
}

# Tab selector mappings for clicking (data-type attributes on Xueqiu)
TAB_SELECTOR_MAPPING = {
    TabName.REMEN: '[data-type="0"]',
    TabName.QIXERSHISI: '[data-type="6"]', 
    TabName.SHIPIN: '[data-type="12"]',
    TabName.JIJIN: '[data-type="5"]',
    TabName.ZIXUN: '[data-type="9"]',
    TabName.DAREN: '[data-type="3"]',
    TabName.SIMU: '[data-type="10"]',
    TabName.ETF: '[data-type="8"]',
}


class CrawlerSettings(BaseSettings):
    """Crawler configuration settings."""
    
    # Base URLs
    base_url: str = "https://xueqiu.com/"
    api_base_url: str = "https://xueqiu.com/statuses/hot/listV2.json"
    
    # Crawling parameters
    max_posts_per_tab: int = Field(default=100, ge=1)
    scroll_timeout: int = Field(default=30000, description="Scroll timeout in ms")
    page_load_timeout: int = Field(default=60000, description="Page load timeout in ms")
    retry_attempts: int = Field(default=3, ge=1)
    retry_delay: float = Field(default=2.0, ge=0.1)
    
    # Concurrency settings
    max_concurrent_tabs: int = Field(default=4, ge=1)
    request_delay: float = Field(default=0.5, ge=0.1)
    
    # Browser settings
    headless: bool = False
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    
    model_config = ConfigDict(env_prefix="XUEQIU_")


class LLMSettings(BaseSettings):
    """LLM API configuration settings."""
    
    # Fireworks API settings
    api_key: str = Field(default="", description="Fireworks API key")
    api_base_url: str = "https://api.fireworks.ai/inference/v1"
    model_name: str = "accounts/sentientfoundation-serverless/models/dobby-mini-unhinged-plus-llama-3-1-8b"
    
    # Request parameters
    max_tokens: int = Field(default=1024, ge=1)
    temperature: float = Field(default=0.3, ge=0, le=2)
    
    # Rate limiting
    requests_per_minute: int = Field(default=5, ge=1)
    max_concurrent_requests: int = Field(default=1, ge=1)
    
    # Retry settings
    retry_attempts: int = Field(default=5, ge=1)
    retry_delay: float = Field(default=10.0, ge=0.1)
    
    model_config = ConfigDict(env_prefix="FIREWORKS_")


class StorageSettings(BaseSettings):
    """Storage configuration settings."""
    
    base_dir: Path = Field(default=Path("storage"))
    
    # Subdirectories
    raw_dir: str = "raw"
    summary_dir: str = "summary"
    reports_dir: str = "reports"
    
    # File naming
    raw_file_prefix: str = "posts_"
    summary_file_prefix: str = "summary_"
    report_filename: str = "final_report.md"
    
    # Incremental save interval (seconds)
    save_interval: int = Field(default=30, ge=5)
    
    model_config = ConfigDict(env_prefix="STORAGE_")


class AppSettings(BaseSettings):
    """Main application settings."""
    
    # Job identification
    job_name: str = Field(
        default_factory=lambda: f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    
    # Logging
    log_level: str = Field(default="INFO")
    log_file: Optional[str] = None
    
    # Component settings
    crawler: CrawlerSettings = Field(default_factory=CrawlerSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    
    # Available tabs
    available_tabs: List[TabName] = Field(
        default_factory=lambda: list(TabName)
    )
    
    model_config = ConfigDict(env_prefix="APP_")
    
    def get_storage_path(self) -> Path:
        """Get the full storage path for current job."""
        return self.storage.base_dir / self.job_name
    
    def get_raw_path(self) -> Path:
        """Get the raw data storage path."""
        return self.get_storage_path() / self.storage.raw_dir
    
    def get_summary_path(self) -> Path:
        """Get the summary storage path."""
        return self.get_storage_path() / self.storage.summary_dir
    
    def get_reports_path(self) -> Path:
        """Get the reports storage path."""
        return self.get_storage_path() / self.storage.reports_dir


# Stock symbol patterns for Chinese markets
STOCK_SYMBOL_PATTERNS = [
    r'\$([A-Z]{1,5})\$',            # US stocks like $AAPL$
    r'SH(\d{6})',                    # Shanghai: SH600519
    r'SZ(\d{6})',                    # Shenzhen: SZ000001
    r'HK(\d{5})',                    # Hong Kong: HK00700
    r'(\d{6})\.(SH|SZ|HK)',         # 600519.SH format
    r'\$([A-Z\d]{1,6})\(([A-Z]{2}\d+)\)\$',  # Complex format
]

# Sentiment keywords for basic classification (Chinese)
SENTIMENT_KEYWORDS = {
    "positive": [
        "涨", "利好", "牛", "买入", "看好", "上涨", "增长", "突破", 
        "强势", "机会", "潜力", "推荐", "优质", "龙头", "翻倍",
        "大涨", "暴涨", "飙升", "新高", "向上"
    ],
    "negative": [
        "跌", "利空", "熊", "卖出", "看空", "下跌", "亏损", "暴跌",
        "弱势", "风险", "警惕", "减持", "抛售", "崩盘", "破位",
        "大跌", "腰斩", "暴雷", "爆仓", "向下"
    ],
    "neutral": [
        "观望", "持有", "震荡", "盘整", "横盘", "等待", "中性",
        "不确定", "维持", "稳定"
    ]
}

# Sector/Theme keywords mapping
SECTOR_KEYWORDS = {
    "Technology": ["芯片", "半导体", "AI", "人工智能", "算力", "云计算", "软件", "互联网"],
    "New Energy": ["锂电", "光伏", "储能", "新能源车", "电池", "充电桩", "风电"],
    "Healthcare": ["医药", "生物", "创新药", "医疗", "疫苗", "CXO", "中药"],
    "Consumer": ["白酒", "消费", "零售", "食品", "家电", "餐饮", "旅游"],
    "Finance": ["银行", "证券", "保险", "券商", "金融", "基金"],
    "Real Estate": ["房地产", "地产", "楼市", "房价", "物业"],
    "Manufacturing": ["制造", "工业", "机械", "汽车", "钢铁", "有色"],
}


def load_settings() -> AppSettings:
    """Load application settings from environment and defaults."""
    return AppSettings()


# Global settings instance
settings = load_settings()