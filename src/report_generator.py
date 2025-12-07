"""
Report Generator module for Xueqiu Crawler.
Aggregates data and generates comprehensive markdown reports.
"""

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .config import AppSettings, SECTOR_KEYWORDS
from .models import (
    CrawlReport,
    PostData,
    PostSummary,
    SentimentType,
    StockMention,
    TabStatistics,
    ThemeAnalysis,
)
from .utils import (
    format_number,
    format_timestamp,
    get_logger,
    get_sentiment_emoji,
    truncate_text,
)


class ReportGenerator:
    """
    Generates comprehensive markdown reports from crawl data.
    Aggregates statistics, sentiment analysis, and key insights.
    """
    
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.logger = get_logger("report_generator")
    
    def aggregate_stock_mentions(self, posts: List[PostData], summaries: List[PostSummary]) -> List[StockMention]:
        summary_map = {s.post_id: s for s in summaries}
        stock_data = defaultdict(lambda: {"count": 0, "positive": 0, "neutral": 0, "negative": 0, "post_ids": [], "companies": []})
        
        for post in posts:
            symbols = set(post.symbols)
            if post.id in summary_map:
                summary = summary_map[post.id]
                sentiment = summary.sentiment
                if summary.companies:
                    for sym in symbols:
                        stock_data[sym]["companies"].extend(summary.companies)
            else:
                sentiment = SentimentType.NEUTRAL
            
            for symbol in symbols:
                stock_data[symbol]["count"] += 1
                stock_data[symbol]["post_ids"].append(post.id)
                if sentiment == SentimentType.POSITIVE:
                    stock_data[symbol]["positive"] += 1
                elif sentiment == SentimentType.NEGATIVE:
                    stock_data[symbol]["negative"] += 1
                else:
                    stock_data[symbol]["neutral"] += 1
        
        mentions = []
        for symbol, data in stock_data.items():
            company_name = None
            if data["companies"]:
                most_common = Counter(data["companies"]).most_common(1)
                if most_common:
                    company_name = most_common[0][0]
            mentions.append(StockMention(symbol=symbol, name=company_name, mention_count=data["count"],
                positive_mentions=data["positive"], neutral_mentions=data["neutral"],
                negative_mentions=data["negative"], sample_post_ids=data["post_ids"][:5]))
        
        mentions.sort(key=lambda x: x.mention_count, reverse=True)
        return mentions
    
    def aggregate_themes(self, summaries: List[PostSummary]) -> List[ThemeAnalysis]:
        theme_data: Dict[str, Dict] = defaultdict(lambda: {"count": 0, "stocks": set(), "positive": 0, "neutral": 0, "negative": 0, "quotes": []})
        
        for summary in summaries:
            for theme in summary.themes + summary.sectors:
                theme_data[theme]["count"] += 1
                theme_data[theme]["stocks"].update(summary.tickers)
                if summary.sentiment == SentimentType.POSITIVE:
                    theme_data[theme]["positive"] += 1
                elif summary.sentiment == SentimentType.NEGATIVE:
                    theme_data[theme]["negative"] += 1
                else:
                    theme_data[theme]["neutral"] += 1
                if len(theme_data[theme]["quotes"]) < 3:
                    theme_data[theme]["quotes"].append(summary.original_text_preview)
        
        analyses = []
        for theme, data in theme_data.items():
            trend = "up" if data["positive"] > data["negative"] * 1.5 else "down" if data["negative"] > data["positive"] * 1.5 else "stable"
            analyses.append(ThemeAnalysis(theme=theme, mention_count=data["count"], related_stocks=list(data["stocks"]),
                sentiment_distribution={"positive": data["positive"], "neutral": data["neutral"], "negative": data["negative"]},
                representative_quotes=data["quotes"], trend_direction=trend))
        analyses.sort(key=lambda x: x.mention_count, reverse=True)
        return analyses
    
    def calculate_overall_sentiment(self, summaries: List[PostSummary]) -> Dict[str, int]:
        distribution = {"positive": 0, "neutral": 0, "negative": 0}
        for summary in summaries:
            if summary.sentiment == SentimentType.POSITIVE:
                distribution["positive"] += 1
            elif summary.sentiment == SentimentType.NEGATIVE:
                distribution["negative"] += 1
            else:
                distribution["neutral"] += 1
        return distribution
    
    def get_top_discussions(self, posts: List[PostData], summaries: List[PostSummary], limit: int = 10) -> List[Dict[str, Any]]:
        summary_map = {s.post_id: s for s in summaries}
        scored_posts = [(p, p.like_count + p.comment_count * 2 + p.retweet_count * 3) for p in posts]
        scored_posts.sort(key=lambda x: x[1], reverse=True)
        
        top_discussions = []
        for post, _ in scored_posts[:limit]:
            summary = summary_map.get(post.id)
            discussion = {"id": post.id, "tab": post.tab, "text": post.text, "author": post.author, "symbols": post.symbols,
                "engagement": {"likes": post.like_count, "comments": post.comment_count, "retweets": post.retweet_count}, "url": post.post_url}
            if summary:
                discussion["sentiment"] = summary.sentiment.value
                discussion["summary"] = summary.summary
            top_discussions.append(discussion)
        return top_discussions
    
    def generate_report(self, posts_by_tab: Dict[str, List[PostData]], summaries_by_tab: Dict[str, List[PostSummary]], tab_stats: Dict[str, TabStatistics]) -> CrawlReport:
        all_posts = [p for posts in posts_by_tab.values() for p in posts]
        all_summaries = [s for sums in summaries_by_tab.values() for s in sums]
        
        return CrawlReport(
            job_name=self.settings.job_name, job_start=datetime.utcnow(), job_end=datetime.utcnow(),
            total_posts_collected=len(all_posts), total_unique_posts=len(set(p.content_hash for p in all_posts)),
            total_posts_summarized=len(all_summaries), tab_statistics=tab_stats,
            stock_mentions=self.aggregate_stock_mentions(all_posts, all_summaries),
            theme_analysis=self.aggregate_themes(all_summaries),
            overall_sentiment=self.calculate_overall_sentiment(all_summaries),
            top_discussions=self.get_top_discussions(all_posts, all_summaries))
    
    def generate_markdown(self, report: CrawlReport) -> str:
        lines = [f"# Xueqiu Discussion Report — {report.job_name}", "",
            f"**Generated:** {format_timestamp(report.job_end)}",
            f"**Total Posts Collected:** {format_number(report.total_posts_collected)}",
            f"**Unique Posts:** {format_number(report.total_unique_posts)}",
            f"**Posts Summarized:** {format_number(report.total_posts_summarized)}", "",
            "## Executive Summary", ""]
        
        total_sentiment = sum(report.overall_sentiment.values())
        if total_sentiment > 0:
            pos_pct = report.overall_sentiment["positive"] / total_sentiment * 100
            neg_pct = report.overall_sentiment["negative"] / total_sentiment * 100
            neu_pct = report.overall_sentiment["neutral"] / total_sentiment * 100
            market_mood = "bullish" if pos_pct > neg_pct else "bearish" if neg_pct > pos_pct else "mixed"
            lines.append(f"Overall market sentiment is **{market_mood}** with {pos_pct:.1f}% positive, {neg_pct:.1f}% negative, and {neu_pct:.1f}% neutral discussions.")
        lines.append("")
        
        lines.extend(["## Key Discussion Points", ""])
        for i, theme in enumerate(report.theme_analysis[:10], 1):
            emoji = get_sentiment_emoji("positive" if theme.trend_direction == "up" else "negative" if theme.trend_direction == "down" else "neutral")
            lines.append(f"{i}. **{theme.theme}** ({theme.mention_count} mentions) {emoji}")
            if theme.representative_quotes:
                lines.append(f"   - *\"{truncate_text(theme.representative_quotes[0], 100)}\"*")
        lines.append("")
        
        lines.extend(["## Most Discussed Stocks", "", "| Rank | Symbol | Mentions | Sentiment | Bullish | Bearish | Neutral |",
            "|------|--------|----------|-----------|---------|---------|---------|"])
        for i, stock in enumerate(report.stock_mentions[:20], 1):
            lines.append(f"| {i} | {stock.symbol} | {stock.mention_count} | {get_sentiment_emoji(stock.overall_sentiment.value)} | {stock.positive_mentions} | {stock.negative_mentions} | {stock.neutral_mentions} |")
        lines.append("")
        
        lines.extend(["## Sentiment Distribution", "",
            f"📈 **Positive:** {report.overall_sentiment['positive']} posts",
            f"➡️ **Neutral:** {report.overall_sentiment['neutral']} posts",
            f"📉 **Negative:** {report.overall_sentiment['negative']} posts", ""])
        
        lines.extend(["## Investment Themes & Sectors", ""])
        for theme in report.theme_analysis[:15]:
            trend_icon = "🔺" if theme.trend_direction == "up" else "🔻" if theme.trend_direction == "down" else "▪️"
            lines.extend([f"### {theme.theme} {trend_icon}", f"- **Mentions:** {theme.mention_count}"])
            if theme.related_stocks:
                lines.append(f"- **Related Stocks:** {', '.join(theme.related_stocks[:5])}")
            lines.extend([f"- **Sentiment:** Positive {theme.sentiment_distribution['positive']}, Negative {theme.sentiment_distribution['negative']}, Neutral {theme.sentiment_distribution['neutral']}", ""])
        
        lines.extend(["## Representative Discussions (Verbatim Quotes)", ""])
        for i, discussion in enumerate(report.top_discussions[:10], 1):
            lines.extend([f"### Discussion #{i}", f"**Tab:** {discussion['tab']} | **Author:** {discussion.get('author', 'Anonymous')}"])
            if discussion.get('symbols'):
                lines.append(f"**Stocks Mentioned:** {', '.join(discussion['symbols'])}")
            if discussion.get('sentiment'):
                lines.append(f"**Sentiment:** {discussion['sentiment']}")
            lines.extend(["", f"> {discussion['text']}", ""])
            eng = discussion['engagement']
            lines.append(f"*👍 {eng['likes']} | 💬 {eng['comments']} | 🔄 {eng['retweets']}*")
            if discussion.get('url'):
                lines.append(f"[View Original]({discussion['url']})")
            lines.extend(["", "---", ""])
        
        lines.extend(["## Data Collection Statistics", "", "| Tab | Posts | Duration (s) | Errors |", "|-----|-------|--------------|--------|"])
        for tab_name, stats in report.tab_statistics.items():
            lines.append(f"| {tab_name} | {stats.valid_posts} | {stats.crawl_duration_seconds:.1f} | {stats.errors_count} |")
        lines.append("")
        
        lines.extend(["## Detailed Stock Analysis", ""])
        for stock in report.stock_mentions[:10]:
            lines.extend([f"### {stock.symbol}", f"**Total Mentions:** {stock.mention_count}", f"**Sentiment Ratio:** {stock.sentiment_ratio:.1%} bullish", ""])
            total = stock.positive_mentions + stock.negative_mentions + stock.neutral_mentions
            if total > 0:
                lines.extend(["```", f"Bullish:  {'█' * int(stock.positive_mentions / total * 20)} ({stock.positive_mentions})",
                    f"Bearish:  {'█' * int(stock.negative_mentions / total * 20)} ({stock.negative_mentions})",
                    f"Neutral:  {'█' * int(stock.neutral_mentions / total * 20)} ({stock.neutral_mentions})", "```"])
            lines.append("")
        
        lines.extend(["---", "", "*Report generated by Xueqiu Investor Discussion Crawler*",
            f"*Data collected from xueqiu.com on {format_timestamp(report.job_end)}*"])
        return "\n".join(lines)
    
    async def generate_and_save(self, posts_by_tab: Dict[str, List[PostData]], summaries_by_tab: Dict[str, List[PostSummary]],
            tab_stats: Dict[str, TabStatistics], storage_manager) -> Tuple[CrawlReport, str]:
        report = self.generate_report(posts_by_tab, summaries_by_tab, tab_stats)
        markdown = self.generate_markdown(report)
        await storage_manager.save_report(markdown)
        await storage_manager.save_report_json(report)
        self.logger.info("Report generated and saved successfully")
        return report, markdown