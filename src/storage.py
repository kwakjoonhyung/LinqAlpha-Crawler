"""
Storage manager for Xueqiu Crawler.
Handles file I/O, incremental updates, and data persistence.
"""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import aiofiles
import orjson

from .config import AppSettings, StorageSettings
from .models import CrawlReport, PostData, PostSummary, TabStatistics
from .utils import ensure_directory, get_logger, safe_filename


class StorageManager:
    """
    Manages all data storage operations including:
    - Raw post data storage (per tab)
    - Summary storage (per tab)
    - Report generation
    - Incremental updates
    """
    
    def __init__(self, settings: AppSettings):
        """
        Initialize storage manager.
        
        Args:
            settings: Application settings
        """
        self.settings = settings
        self.logger = get_logger("storage")
        
        # Storage paths
        self.base_path = settings.get_storage_path()
        self.raw_path = settings.get_raw_path()
        self.summary_path = settings.get_summary_path()
        self.reports_path = settings.get_reports_path()
        
        # In-memory caches for deduplication
        self._seen_hashes: Set[str] = set()
        self._post_counts: Dict[str, int] = {}
        
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()
        
        # Initialize directories
        self._init_directories()
    
    def _init_directories(self):
        """Create all necessary directories."""
        ensure_directory(self.base_path)
        ensure_directory(self.raw_path)
        ensure_directory(self.summary_path)
        ensure_directory(self.reports_path)
        self.logger.info(f"Storage initialized at: {self.base_path}")
    
    def _get_raw_filepath(self, tab: str) -> Path:
        """Get filepath for raw posts of a tab."""
        safe_tab = safe_filename(tab)
        return self.raw_path / f"{self.settings.storage.raw_file_prefix}{safe_tab}.json"
    
    def _get_summary_filepath(self, tab: str) -> Path:
        """Get filepath for summaries of a tab."""
        safe_tab = safe_filename(tab)
        return self.summary_path / f"{self.settings.storage.summary_file_prefix}{safe_tab}.json"
    
    def _get_report_filepath(self) -> Path:
        """Get filepath for final report."""
        return self.reports_path / self.settings.storage.report_filename
    
    async def load_existing_posts(self, tab: str) -> List[PostData]:
        """
        Load existing posts for a tab from disk.
        
        Args:
            tab: Tab name
            
        Returns:
            List of existing posts
        """
        filepath = self._get_raw_filepath(tab)
        
        if not filepath.exists():
            return []
        
        try:
            async with aiofiles.open(filepath, 'r', encoding='utf-8') as f:
                content = await f.read()
                data = orjson.loads(content)
                
                posts = []
                for item in data.get("posts", []):
                    try:
                        post = PostData(**item)
                        posts.append(post)
                        self._seen_hashes.add(post.content_hash)
                    except Exception as e:
                        self.logger.warning(f"Failed to parse post: {e}")
                
                self._post_counts[tab] = len(posts)
                self.logger.info(f"Loaded {len(posts)} existing posts for tab '{tab}'")
                return posts
                
        except Exception as e:
            self.logger.error(f"Error loading posts for tab '{tab}': {e}")
            return []
    
    async def save_posts(
        self, 
        tab: str, 
        posts: List[PostData],
        incremental: bool = True
    ) -> int:
        """
        Save posts for a tab to disk.
        
        Args:
            tab: Tab name
            posts: List of posts to save
            incremental: If True, merge with existing posts
            
        Returns:
            Number of new posts saved
        """
        async with self._lock:
            filepath = self._get_raw_filepath(tab)
            
            # Filter duplicates
            new_posts = []
            for post in posts:
                if post.content_hash not in self._seen_hashes:
                    self._seen_hashes.add(post.content_hash)
                    new_posts.append(post)
            
            if not new_posts and not incremental:
                return 0
            
            # Load existing posts if incremental
            existing_posts = []
            if incremental and filepath.exists():
                existing_posts = await self.load_existing_posts(tab)
            
            # Merge posts
            all_posts = existing_posts + new_posts
            
            # Prepare data for saving
            save_data = {
                "metadata": {
                    "tab": tab,
                    "job_name": self.settings.job_name,
                    "total_posts": len(all_posts),
                    "new_posts_this_save": len(new_posts),
                    "last_updated": datetime.utcnow().isoformat(),
                },
                "posts": [post.model_dump() for post in all_posts]
            }
            
            # Save to file
            try:
                async with aiofiles.open(filepath, 'wb') as f:
                    await f.write(orjson.dumps(
                        save_data,
                        option=orjson.OPT_INDENT_2 | orjson.OPT_NON_STR_KEYS
                    ))
                
                self._post_counts[tab] = len(all_posts)
                self.logger.info(
                    f"Saved {len(new_posts)} new posts for tab '{tab}' "
                    f"(total: {len(all_posts)})"
                )
                return len(new_posts)
                
            except Exception as e:
                self.logger.error(f"Error saving posts for tab '{tab}': {e}")
                raise
    
    async def load_existing_summaries(self, tab: str) -> List[PostSummary]:
        """
        Load existing summaries for a tab from disk.
        
        Args:
            tab: Tab name
            
        Returns:
            List of existing summaries
        """
        filepath = self._get_summary_filepath(tab)
        
        if not filepath.exists():
            return []
        
        try:
            async with aiofiles.open(filepath, 'r', encoding='utf-8') as f:
                content = await f.read()
                data = orjson.loads(content)
                
                summaries = []
                for item in data.get("summaries", []):
                    try:
                        summary = PostSummary(**item)
                        summaries.append(summary)
                    except Exception as e:
                        self.logger.warning(f"Failed to parse summary: {e}")
                
                self.logger.info(f"Loaded {len(summaries)} existing summaries for tab '{tab}'")
                return summaries
                
        except Exception as e:
            self.logger.error(f"Error loading summaries for tab '{tab}': {e}")
            return []
    
    async def save_summaries(
        self,
        tab: str,
        summaries: List[PostSummary],
        incremental: bool = True
    ) -> int:
        """
        Save summaries for a tab to disk.
        
        Args:
            tab: Tab name
            summaries: List of summaries to save
            incremental: If True, merge with existing summaries
            
        Returns:
            Number of new summaries saved
        """
        async with self._lock:
            filepath = self._get_summary_filepath(tab)
            
            # Track by post_id to avoid duplicates
            existing_summaries = []
            existing_ids = set()
            
            if incremental and filepath.exists():
                existing_summaries = await self.load_existing_summaries(tab)
                existing_ids = {s.post_id for s in existing_summaries}
            
            # Filter new summaries
            new_summaries = [s for s in summaries if s.post_id not in existing_ids]
            
            # Merge summaries
            all_summaries = existing_summaries + new_summaries
            
            # Prepare data for saving
            save_data = {
                "metadata": {
                    "tab": tab,
                    "job_name": self.settings.job_name,
                    "total_summaries": len(all_summaries),
                    "new_summaries_this_save": len(new_summaries),
                    "last_updated": datetime.utcnow().isoformat(),
                },
                "summaries": [s.model_dump() for s in all_summaries]
            }
            
            # Save to file
            try:
                async with aiofiles.open(filepath, 'wb') as f:
                    await f.write(orjson.dumps(
                        save_data,
                        option=orjson.OPT_INDENT_2 | orjson.OPT_NON_STR_KEYS
                    ))
                
                self.logger.info(
                    f"Saved {len(new_summaries)} new summaries for tab '{tab}' "
                    f"(total: {len(all_summaries)})"
                )
                return len(new_summaries)
                
            except Exception as e:
                self.logger.error(f"Error saving summaries for tab '{tab}': {e}")
                raise
    
    async def save_report(self, report_content: str) -> Path:
        """
        Save final report to disk.
        
        Args:
            report_content: Markdown report content
            
        Returns:
            Path to saved report
        """
        filepath = self._get_report_filepath()
        
        try:
            async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
                await f.write(report_content)
            
            self.logger.info(f"Report saved to: {filepath}")
            return filepath
            
        except Exception as e:
            self.logger.error(f"Error saving report: {e}")
            raise
    
    async def save_report_json(self, report: CrawlReport) -> Path:
        """
        Save report data as JSON.
        
        Args:
            report: Crawl report object
            
        Returns:
            Path to saved JSON
        """
        filepath = self.reports_path / "report_data.json"
        
        try:
            async with aiofiles.open(filepath, 'wb') as f:
                await f.write(orjson.dumps(
                    report.model_dump(),
                    option=orjson.OPT_INDENT_2 | orjson.OPT_NON_STR_KEYS
                ))
            
            self.logger.info(f"Report data saved to: {filepath}")
            return filepath
            
        except Exception as e:
            self.logger.error(f"Error saving report data: {e}")
            raise
    
    async def get_all_posts(self) -> Dict[str, List[PostData]]:
        """
        Load all posts from all tabs.
        
        Returns:
            Dictionary mapping tab names to posts
        """
        all_posts = {}
        
        for file in self.raw_path.glob(f"{self.settings.storage.raw_file_prefix}*.json"):
            tab = file.stem.replace(self.settings.storage.raw_file_prefix, "")
            posts = await self.load_existing_posts(tab)
            all_posts[tab] = posts
        
        return all_posts
    
    async def get_all_summaries(self) -> Dict[str, List[PostSummary]]:
        """
        Load all summaries from all tabs.
        
        Returns:
            Dictionary mapping tab names to summaries
        """
        all_summaries = {}
        
        for file in self.summary_path.glob(f"{self.settings.storage.summary_file_prefix}*.json"):
            tab = file.stem.replace(self.settings.storage.summary_file_prefix, "")
            summaries = await self.load_existing_summaries(tab)
            all_summaries[tab] = summaries
        
        return all_summaries
    
    def is_duplicate(self, content_hash: str) -> bool:
        """
        Check if content hash already exists.
        
        Args:
            content_hash: Hash to check
            
        Returns:
            True if duplicate
        """
        return content_hash in self._seen_hashes
    
    def get_post_count(self, tab: Optional[str] = None) -> int:
        """
        Get post count for a tab or total.
        
        Args:
            tab: Tab name (None for total)
            
        Returns:
            Post count
        """
        if tab:
            return self._post_counts.get(tab, 0)
        return sum(self._post_counts.values())
    
    async def cleanup(self):
        """Cleanup resources."""
        self._seen_hashes.clear()
        self._post_counts.clear()
        self.logger.info("Storage manager cleaned up")


class IncrementalSaver:
    """
    Helper class for periodic incremental saves.
    Ensures data is saved at regular intervals during crawling.
    """
    
    def __init__(
        self,
        storage: StorageManager,
        interval_seconds: int = 30
    ):
        """
        Initialize incremental saver.
        
        Args:
            storage: Storage manager instance
            interval_seconds: Save interval in seconds
        """
        self.storage = storage
        self.interval = interval_seconds
        self.logger = get_logger("incremental_saver")
        
        self._pending_posts: Dict[str, List[PostData]] = {}
        self._pending_summaries: Dict[str, List[PostSummary]] = {}
        self._lock = asyncio.Lock()
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start the incremental saver background task."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._save_loop())
        self.logger.info(f"Incremental saver started (interval: {self.interval}s)")
    
    async def stop(self):
        """Stop the incremental saver and save any pending data."""
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        # Final save of pending data
        await self._flush()
        self.logger.info("Incremental saver stopped")
    
    async def add_posts(self, tab: str, posts: List[PostData]):
        """
        Add posts to pending queue.
        
        Args:
            tab: Tab name
            posts: Posts to add
        """
        async with self._lock:
            if tab not in self._pending_posts:
                self._pending_posts[tab] = []
            self._pending_posts[tab].extend(posts)
    
    async def add_summaries(self, tab: str, summaries: List[PostSummary]):
        """
        Add summaries to pending queue.
        
        Args:
            tab: Tab name
            summaries: Summaries to add
        """
        async with self._lock:
            if tab not in self._pending_summaries:
                self._pending_summaries[tab] = []
            self._pending_summaries[tab].extend(summaries)
    
    async def _save_loop(self):
        """Background loop for periodic saves."""
        while self._running:
            try:
                await asyncio.sleep(self.interval)
                await self._flush()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in save loop: {e}")
    
    async def _flush(self):
        """Flush all pending data to disk."""
        async with self._lock:
            # Save pending posts
            for tab, posts in self._pending_posts.items():
                if posts:
                    try:
                        await self.storage.save_posts(tab, posts, incremental=True)
                    except Exception as e:
                        self.logger.error(f"Error saving posts for {tab}: {e}")
            
            # Save pending summaries
            for tab, summaries in self._pending_summaries.items():
                if summaries:
                    try:
                        await self.storage.save_summaries(tab, summaries, incremental=True)
                    except Exception as e:
                        self.logger.error(f"Error saving summaries for {tab}: {e}")
            
            # Clear pending data
            self._pending_posts.clear()
            self._pending_summaries.clear()
