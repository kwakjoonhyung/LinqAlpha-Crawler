"""
Xueqiu Crawler module.
Implements Playwright-based browser automation to bypass API anti-bot protections.
Includes robust selector handling, modal closing, and concurrent tab crawling.
"""

import asyncio
import os
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

from .config import AppSettings, TabName, TAB_SELECTOR_MAPPING
from .models import PostData, TabStatistics
from .utils import (
    clean_text,
    extract_stock_symbols,
    extract_urls,
    generate_content_hash,
    get_logger,
)


class XueqiuCrawler:
    """
    Asynchronous crawler for Xueqiu investor discussions.
    Uses Playwright browser automation to bypass API blocking.
    """
    
    def __init__(self, settings: AppSettings):
        """
        Initialize crawler.
        
        Args:
            settings: Application settings
        """
        self.settings = settings
        self.logger = get_logger("crawler")
        self._stats: Dict[str, TabStatistics] = {}
        self._seen_ids: Set[str] = set()
        self._post_callback: Optional[Callable] = None
        
        # Check Playwright availability
        try:
            import playwright
            self._playwright_available = True
        except ImportError:
            self._playwright_available = False
            self.logger.warning(
                "Playwright not installed. "
                "Run: pip install playwright && playwright install chromium"
            )

    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        pass
        
    async def close(self):
        """Close any open resources."""
        pass
    
    def set_post_callback(self, callback: Callable):
        """
        Set callback function for processing posts.
        
        Args:
            callback: Async function to call with each batch of posts
        """
        self._post_callback = callback
    
    async def crawl_tab(
        self, 
        tab: TabName, 
        max_posts: Optional[int] = None
    ) -> List[PostData]:
        """
        Crawl posts from a single tab using Playwright.
        
        Args:
            tab: Tab to crawl
            max_posts: Maximum posts to collect
            
        Returns:
            List of collected posts
        """
        tab_name = tab.value
        max_posts = max_posts or self.settings.crawler.max_posts_per_tab
        
        self.logger.info(f"Starting crawl for tab '{tab_name}' using Playwright...")
        
        # Initialize statistics
        self._stats[tab_name] = TabStatistics(
            tab_name=tab_name,
            total_posts=0,
            valid_posts=0,
            duplicate_posts=0
        )
        
        start_time = datetime.utcnow()
        posts = []
        
        try:
            if self._playwright_available:
                posts = await self._crawl_tab_via_playwright(tab, max_posts)
            else:
                self.logger.error(
                    "Playwright is required but not installed. "
                    "Run: pip install playwright && playwright install chromium"
                )
            
            # Call callback if set (for incremental saving)
            if self._post_callback and posts:
                await self._post_callback(tab_name, posts)
                
        except Exception as e:
            self.logger.error(f"Error crawling {tab_name}: {e}")
            self._stats[tab_name].errors_count += 1
        
        # Update statistics
        end_time = datetime.utcnow()
        self._stats[tab_name].total_posts = len(posts)
        self._stats[tab_name].valid_posts = len(posts)
        self._stats[tab_name].crawl_duration_seconds = (end_time - start_time).total_seconds()
        
        self.logger.info(
            f"Completed crawl for {tab_name}: {len(posts)} posts in "
            f"{self._stats[tab_name].crawl_duration_seconds:.1f}s"
        )
        
        return posts

    async def _handle_login_modal(self, page):
        """
        Close login modal if it appears.
        
        Args:
            page: Playwright page object
        """
        try:
            # Common selectors for Xueqiu login close buttons
            close_selectors = [
                ".modal__close", 
                "[class*='modal'] [class*='close']", 
                "a.close",
                "[aria-label='Close']"
            ]
            for selector in close_selectors:
                if await page.locator(selector).is_visible(timeout=1000):
                    self.logger.info("Closing login modal...")
                    await page.click(selector)
                    await page.wait_for_timeout(500)
                    return
        except Exception:
            pass

    async def _crawl_tab_via_playwright(
        self, 
        tab: TabName, 
        max_posts: int
    ) -> List[PostData]:
        """
        Crawl tab using Playwright browser automation.
        
        Args:
            tab: Tab to crawl
            max_posts: Maximum posts to collect
            
        Returns:
            List of collected posts
        """
        tab_name = tab.value
        posts = []
        
        try:
            from playwright.async_api import async_playwright
            
            async with async_playwright() as p:
                # Launch browser with anti-detection settings
                browser = await p.chromium.launch(
                    headless=self.settings.crawler.headless,
                    args=["--disable-blink-features=AutomationControlled"]
                )
                
                context = await browser.new_context(
                    user_agent=self.settings.crawler.user_agent,
                    viewport={"width": 1366, "height": 768}
                )
                
                # Add cookies if available from environment
                cookie_str = os.environ.get("XUEQIU_COOKIE")
                if cookie_str:
                    cookies = []
                    for item in cookie_str.split(";"):
                        if "=" in item:
                            k, v = item.strip().split("=", 1)
                            cookies.append({
                                "name": k, 
                                "value": v, 
                                "domain": ".xueqiu.com", 
                                "path": "/"
                            })
                    if cookies:
                        await context.add_cookies(cookies)
                        self.logger.info("Added cookies from environment")

                page = await context.new_page()
                
                # Navigate to homepage
                self.logger.info(f"[{tab_name}] Navigating to homepage...")
                await page.goto(
                    "https://xueqiu.com/", 
                    wait_until="domcontentloaded", 
                    timeout=60000
                )
                await page.wait_for_timeout(3000)  # Initial load wait
                
                # Handle initial popup
                await self._handle_login_modal(page)
                
                # Click on target tab
                try:
                    self.logger.info(f"[{tab_name}] Clicking tab...")
                    # Try clicking by text first
                    tab_locator = page.locator(f"//a[contains(text(), '{tab_name}')]")
                    if await tab_locator.count() > 0:
                        await tab_locator.first.click()
                    else:
                        # Fallback to data-type selector
                        selector = TAB_SELECTOR_MAPPING.get(tab)
                        if selector:
                            await page.click(selector)
                    
                    await page.wait_for_timeout(2000)
                    
                except Exception as e:
                    self.logger.warning(
                        f"[{tab_name}] Tab click issue: {e}. Trying to crawl anyway."
                    )

                # Scroll and collect posts
                scroll_count = 0
                max_scrolls = (max_posts // 5) + 10  # Extra scrolls for safety
                no_new_content_count = 0
                
                # Robust selectors for post elements
                post_selectors = [
                    "div[class*='AnonymousHome']", 
                    "div[class*='timeline-live']",
                    "div[class*='TimelineItem_item_']", 
                    ".timeline__item",
                    ".status-item",
                    "article",
                    "div.flow-item",       
                    "div.feed-item",       
                    "div[class*='item__']" 
                ]
                combined_selector = ", ".join(post_selectors)
                
                while len(posts) < max_posts and scroll_count < max_scrolls:
                    # Wait for items to be present
                    try:
                        await page.wait_for_selector(combined_selector, timeout=3000)
                    except Exception:
                        self.logger.debug(f"[{tab_name}] Waiting for content...")

                    items = await page.locator(combined_selector).all()
                    
                    if not items:
                        self.logger.warning(f"[{tab_name}] No items found on screen.")
                    
                    current_batch_count = len(posts)
                    
                    for item in items:
                        if len(posts) >= max_posts:
                            break
                        
                        try:
                            # Extract text content
                            text = await item.inner_text()
                            if len(text) < 5:
                                continue  # Too short
                            
                            text = clean_text(text)
                            post_id = generate_content_hash(text)[:16]
                            
                            # Skip duplicates
                            if post_id in self._seen_ids:
                                continue
                            self._seen_ids.add(post_id)
                            
                            # Create PostData object
                            post = PostData(
                                id=post_id,
                                text=text,
                                html="",
                                timestamp=datetime.utcnow(),
                                tab=tab_name,
                                symbols=extract_stock_symbols(text),
                                urls=extract_urls(text)
                            )
                            
                            if post.is_valid():
                                posts.append(post)
                                
                        except Exception:
                            continue
                    
                    # Scroll down
                    await self._handle_login_modal(page)  # Check for modal again
                    await page.evaluate("window.scrollBy(0, 1000)")
                    await page.wait_for_timeout(2000)  # Wait for infinite scroll loading
                    
                    # Check progress
                    if len(posts) == current_batch_count:
                        no_new_content_count += 1
                        self.logger.debug(
                            f"[{tab_name}] No new posts found (Retry {no_new_content_count})"
                        )
                    else:
                        no_new_content_count = 0
                        
                    if no_new_content_count > 5:
                        self.logger.info(f"[{tab_name}] Reached end of feed or blocked.")
                        break
                        
                    scroll_count += 1
                    self.logger.info(f"[{tab_name}] Collected {len(posts)} posts so far...")
                
                await browser.close()
                
        except Exception as e:
            self.logger.error(f"Playwright crawl error for {tab_name}: {e}")
        
        return posts

    async def crawl_tabs(
        self, 
        tabs: List[TabName], 
        max_posts_per_tab: Optional[int] = None
    ) -> Dict[str, List[PostData]]:
        """
        Crawl multiple tabs concurrently.
        
        Args:
            tabs: List of tabs to crawl
            max_posts_per_tab: Maximum posts per tab
            
        Returns:
            Dictionary mapping tab names to posts
        """
        self.logger.info(f"Starting concurrent crawl for {len(tabs)} tabs")
        
        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(self.settings.crawler.max_concurrent_tabs)
        
        async def crawl_with_semaphore(tab: TabName):
            async with semaphore:
                return await self.crawl_tab(tab, max_posts_per_tab)

        tasks = [crawl_with_semaphore(tab) for tab in tabs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        all_posts = {}
        for tab, result in zip(tabs, results):
            if isinstance(result, Exception):
                self.logger.error(f"Tab {tab.value} failed: {result}")
                all_posts[tab.value] = []
            else:
                all_posts[tab.value] = result
        
        total = sum(len(posts) for posts in all_posts.values())
        self.logger.info(f"Crawl complete: {total} total posts from {len(all_posts)} tabs")
        
        return all_posts

    def get_statistics(self) -> Dict[str, TabStatistics]:
        """
        Get crawl statistics for all tabs.
        
        Returns:
            Dictionary mapping tab names to statistics
        """
        return self._stats.copy()