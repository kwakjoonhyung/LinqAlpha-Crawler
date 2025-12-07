"""
LLM Summarization module for Xueqiu Crawler.
Uses Fireworks AI API with OpenAI SDK for post summarization and entity extraction.
"""

import asyncio
import json
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI, APIError, RateLimitError, APITimeoutError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import AppSettings
from .models import PostData, PostSummary, SentimentType
from .utils import (
    classify_sentiment_basic,
    get_logger,
    identify_sectors,
    truncate_text,
    RateLimiter,
)


# System prompt for LLM summarization
SUMMARIZATION_PROMPT = """You are an expert financial analyst specializing in Chinese stock markets. 
Analyze the following investor discussion post from Xueqiu (雪球), a Chinese social investing platform.

Your task is to extract insights and output them STRICTLY IN ENGLISH.

Tasks:
1. Provide a concise summary (1-2 sentences) IN ENGLISH.
2. Extract key discussion points IN ENGLISH.
3. Identify mentioned stock tickers (format: SH/SZ/HK + code).
4. Identify company names (Translate Chinese names to English, e.g., "贵州茅台" -> "Kweichow Moutai").
5. Identify investment themes and sectors (Use standard English terms like "Technology", "Finance").
6. Analyze sentiment (positive/neutral/negative) and provide reasoning IN ENGLISH.

Respond in JSON format with the following structure:
{
    "summary": "Brief summary of the post in English",
    "key_points": ["Point 1 in English", "Point 2 in English"],
    "tickers": ["SH600519", "SZ000001"],
    "companies": ["Kweichow Moutai", "Ping An Bank"],
    "themes": ["Value Investing", "White Liquor"],
    "sectors": ["Consumption", "Finance"],
    "sentiment": "positive",
    "sentiment_score": 0.8,
    "sentiment_reasoning": "The author expresses optimism about... (in English)"
}

Important Constraints:
- OUTPUT LANGUAGE: ALL text fields (summary, key_points, companies, themes, reasoning) MUST BE IN ENGLISH.
- Translate any Chinese text found in the post into English for the summary and reasoning.
- If no stocks are mentioned, return empty arrays.
- Sentiment score should be between -1.0 (very negative) and 1.0 (very positive).
- Do not hallucinate or add information not present in the original post."""


class LLMSummarizer:
    """
    LLM-based post summarizer using Fireworks AI.
    Extracts entities, sentiment, and key points from posts.
    """
    
    def __init__(self, settings: AppSettings):
        """
        Initialize LLM summarizer.
        
        Args:
            settings: Application settings
        """
        self.settings = settings
        self.llm_settings = settings.llm
        self.logger = get_logger("llm_summarizer")
        
        # OpenAI async client (for Fireworks API)
        self.client: Optional[AsyncOpenAI] = None
        
        # Rate limiter
        self._rate_limiter = RateLimiter(
            calls_per_second=self.llm_settings.requests_per_minute / 60.0
        )
        
        # Statistics tracking
        self._total_requests = 0
        self._successful_requests = 0
        self._failed_requests = 0
        self._total_tokens = 0
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self._init_client()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def _init_client(self):
        """Initialize OpenAI client for Fireworks API."""
        self.client = AsyncOpenAI(
            api_key=self.llm_settings.api_key,
            base_url=self.llm_settings.api_base_url,
            timeout=60.0,
            max_retries=0  # Use tenacity for retries instead
        )
        self.logger.info(
            f"OpenAI SDK initialized for Fireworks "
            f"(RPM: {self.llm_settings.requests_per_minute})"
        )
    
    async def close(self):
        """Close the client."""
        if self.client:
            await self.client.close()
            self.client = None
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=2, max=20),
        retry=retry_if_exception_type((APIError, APITimeoutError, RateLimitError)),
        reraise=True
    )
    async def _call_api(self, messages: List[Dict]) -> Optional[str]:
        """
        Call the LLM API with retry logic.
        
        Args:
            messages: List of message dictionaries
            
        Returns:
            Response content or None
        """
        await self._rate_limiter.wait()
        
        try:
            response = await self.client.chat.completions.create(
                model=self.llm_settings.model_name,
                messages=messages,
                max_tokens=self.llm_settings.max_tokens,
                temperature=self.llm_settings.temperature,
                response_format={"type": "json_object"} 
            )
            
            self._total_requests += 1
            
            content = response.choices[0].message.content
            
            if not content:
                self.logger.warning("API returned empty content.")
                return None

            self._successful_requests += 1
            if response.usage:
                self._total_tokens += response.usage.total_tokens
            
            return content

        except RateLimitError:
            self.logger.warning("Rate Limit (429). Retrying...")
            raise  # Tenacity will handle retry
        except APIError as e:
            self.logger.warning(f"API Error ({e.status_code}): {e.message}")
            raise  # Tenacity will handle retry
            
    def _parse_llm_response(self, response: str, post: PostData) -> PostSummary:
        """
        Parse LLM response into PostSummary.
        
        Args:
            response: JSON response string
            post: Original post data
            
        Returns:
            Parsed PostSummary
        """
        try:
            data = json.loads(response)
            sentiment_str = data.get("sentiment", "neutral").lower()
            
            try:
                sentiment = SentimentType(sentiment_str)
            except ValueError:
                sentiment = SentimentType.NEUTRAL
            
            return PostSummary(
                post_id=post.id,
                post_hash=post.content_hash,
                tab=post.tab,
                summary=data.get("summary", ""),
                key_points=data.get("key_points", []),
                tickers=data.get("tickers", []) + post.symbols,
                companies=data.get("companies", []),
                themes=data.get("themes", []),
                sectors=data.get("sectors", []),
                sentiment=sentiment,
                sentiment_score=float(data.get("sentiment_score", 0.0)),
                sentiment_reasoning=data.get("sentiment_reasoning"),
                model_used=self.llm_settings.model_name,
                original_text_preview=truncate_text(post.text, 200)
            )
        except json.JSONDecodeError:
            return self._create_fallback_summary(post)
    
    def _create_fallback_summary(self, post: PostData) -> PostSummary:
        """
        Create fallback summary using basic keyword analysis.
        
        Args:
            post: Post data
            
        Returns:
            Basic PostSummary
        """
        sentiment_label, sentiment_score = classify_sentiment_basic(post.text)
        sentiment = SentimentType(sentiment_label)
        sectors = identify_sectors(post.text)
        
        return PostSummary(
            post_id=post.id,
            post_hash=post.content_hash,
            tab=post.tab,
            summary=truncate_text(post.text, 100) + " (Auto-generated)",
            key_points=[],
            tickers=post.symbols,
            companies=[],
            themes=[],
            sectors=sectors,
            sentiment=sentiment,
            sentiment_score=sentiment_score if sentiment == SentimentType.POSITIVE else -sentiment_score,
            sentiment_reasoning="Basic keyword-based analysis",
            model_used="fallback",
            original_text_preview=truncate_text(post.text, 200)
        )
    
    async def summarize_post(self, post: PostData) -> PostSummary:
        """
        Summarize a single post.
        
        Args:
            post: Post to summarize
            
        Returns:
            PostSummary
        """
        messages = [
            {"role": "system", "content": SUMMARIZATION_PROMPT},
            {"role": "user", "content": f"Post content:\n\n{post.text}"}
        ]
        
        try:
            response = await self._call_api(messages)
            if response:
                return self._parse_llm_response(response, post)
        except Exception as e:
            self.logger.debug(f"LLM call failed: {e}")
            self._failed_requests += 1
            
        return self._create_fallback_summary(post)
    
    async def summarize_posts(
        self,
        posts: List[PostData],
        batch_size: Optional[int] = None
    ) -> List[PostSummary]:
        """
        Summarize multiple posts.
        
        Args:
            posts: List of posts to summarize
            batch_size: Number of concurrent requests
            
        Returns:
            List of PostSummary objects
        """
        if batch_size is None:
            batch_size = self.llm_settings.max_concurrent_requests
            
        summaries = []
        total = len(posts)
        
        self.logger.info(f"Starting summarization of {total} posts (Batch size: {batch_size})")
        
        for i in range(0, total, batch_size):
            batch = posts[i:i + batch_size]
            tasks = [self.summarize_post(post) for post in batch]
            
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in batch_results:
                if isinstance(result, PostSummary):
                    summaries.append(result)
            
            progress = min(i + batch_size, total)
            self.logger.info(f"Summarized {progress}/{total} posts...")
            
        return summaries
    
    async def summarize_tab_posts(
        self, 
        tab: str, 
        posts: List[PostData]
    ) -> List[PostSummary]:
        """
        Summarize all posts from a tab.
        
        Args:
            tab: Tab name
            posts: List of posts
            
        Returns:
            List of PostSummary objects
        """
        return await self.summarize_posts(posts)
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get summarization statistics.
        
        Returns:
            Statistics dictionary
        """
        return {
            "total_requests": self._total_requests,
            "successful_requests": self._successful_requests,
            "failed_requests": self._failed_requests,
            "total_tokens": self._total_tokens
        }


class BatchSummarizer:
    """Helper class for batch processing summaries across tabs."""
    
    def __init__(self, settings: AppSettings, llm_summarizer: LLMSummarizer):
        """
        Initialize batch summarizer.
        
        Args:
            settings: Application settings
            llm_summarizer: LLM summarizer instance
        """
        self.settings = settings
        self.llm = llm_summarizer
        self.logger = get_logger("batch_summarizer")
    
    async def process_all_tabs(
        self, 
        posts_by_tab: Dict[str, List[PostData]]
    ) -> Dict[str, List[PostSummary]]:
        """
        Process summaries for all tabs.
        
        Args:
            posts_by_tab: Dictionary of posts by tab
            
        Returns:
            Dictionary of summaries by tab
        """
        summaries_by_tab = {}
        for tab, posts in posts_by_tab.items():
            self.logger.info(f"Processing tab '{tab}' with {len(posts)} posts")
            summaries = await self.llm.summarize_tab_posts(tab, posts)
            summaries_by_tab[tab] = summaries
        return summaries_by_tab


class MockLLMSummarizer(LLMSummarizer):
    """Mock LLM summarizer for testing without API calls."""
    
    async def _call_api(self, messages: List[Dict]) -> Optional[str]:
        """Return None to trigger fallback summarization."""
        return None
    
    async def summarize_post(self, post: PostData) -> PostSummary:
        """Always use fallback summarization."""
        return self._create_fallback_summary(post)