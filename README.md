# Xueqiu Investor Discussion Crawler

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/Playwright-Automation-green.svg" alt="Playwright">
  <img src="https://img.shields.io/badge/LLM-Fireworks%20AI-orange.svg" alt="LLM">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
</p>

A Python-based crawler that captures investor discussions from **Xueqiu (雪球)** — one of China's leading social investing platforms — and generates structured investor sentiment reports for **Hedge Fund Analysts**.

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [System Architecture](#-system-architecture)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Usage](#-usage)
- [Output Structure](#-output-structure)
- [Report Contents](#-report-contents)
- [Available Tabs](#-available-tabs)
- [Technical Details](#-technical-details)
- [Troubleshooting](#-troubleshooting)
- [License](#-license)

---

## 🎯 Overview

This project provides a complete **data-to-insight pipeline** that:

1. **Crawls** investor discussions from multiple tabs on Xueqiu
2. **Extracts** structured data including text, metadata, stock tickers, and engagement metrics
3. **Summarizes** posts using LLM (Fireworks API) to extract entities and sentiment
4. **Generates** comprehensive markdown reports with market insights

The solution was built using **Python 3.10** with a modular architecture ensuring **robustness**, **scalability**, and **data integrity**.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| **Browser Automation** | Uses Playwright for reliable crawling that bypasses API anti-bot protections |
| **Concurrent Crawling** | Asynchronous crawling of multiple tabs simultaneously using `asyncio` |
| **Flexible Tab Selection** | Crawl specific tabs or all 8 available tabs |
| **Robust Error Handling** | Automatic retries with exponential backoff, graceful failure handling |
| **Incremental Saving** | Data saved continuously during crawling to prevent data loss |
| **LLM Integration** | Fireworks API (Llama-3-8b-instruct) for intelligent summarization |
| **Deduplication** | Content-hash based duplicate detection using xxhash |
| **Comprehensive Reports** | Markdown reports with stock analysis, sentiment trends, and verbatim quotes |

---

## 🏗 System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              main.py                                     │
│                         (CLI Entry Point)                                │
│    Orchestrates the complete data-to-insight pipeline                    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           Core Components                                │
├─────────────────┬─────────────────┬─────────────────┬───────────────────┤
│   crawler.py    │  llm_summarizer │   storage.py    │ report_generator  │
│                 │      .py        │                 │       .py         │
├─────────────────┼─────────────────┼─────────────────┼───────────────────┤
│ • Playwright    │ • OpenAI SDK    │ • Incremental   │ • Markdown        │
│ • asyncio       │ • Fireworks AI  │   Saver         │   Generation      │
│ • Dynamic JS    │ • Llama-3-8b    │ • JSON Storage  │ • Sentiment       │
│   Rendering     │ • Sentiment     │ • Deduplication │   Analysis        │
│ • Infinite      │   Scoring       │                 │ • Stock Rankings  │
│   Scrolling     │                 │                 │                   │
└─────────────────┴─────────────────┴─────────────────┴───────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Supporting Modules                               │
├─────────────────────────────┬───────────────────────────────────────────┤
│         config.py           │              models.py                     │
├─────────────────────────────┼───────────────────────────────────────────┤
│ • Environment Variables     │ • Pydantic Data Models                    │
│ • Tab Mappings              │ • Type Validation                         │
│ • Sentiment Keywords        │ • PostData, PostSummary                   │
│ • Sector Classifications    │ • CrawlReport, TabStatistics              │
└─────────────────────────────┴───────────────────────────────────────────┘
```

### Core Components

| Component | File | Description |
|-----------|------|-------------|
| **Asynchronous Crawler** | `crawler.py` | Utilizes Playwright and asyncio to handle dynamic JavaScript rendering and infinite scrolling. Implements robust selector strategies to handle varying DOM structures across different tabs (e.g., special handling for the 7x24 news stream). |
| **Data Modeling** | `models.py` | Employs Pydantic for strict type validation, ensuring data consistency across the pipeline. |
| **LLM Integration** | `llm_summarizer.py` | Integrated OpenAI SDK compatible with Fireworks AI. Uses Llama-3-8b-instruct for extraction, translation, and sentiment scoring. |
| **Storage Layer** | `storage.py` | Implements an IncrementalSaver to ensure data persistence during long-running tasks, utilizing JSON for structured storage. |
| **Reporting** | `report_generator.py` | Automated generation of Markdown reports containing executive summaries, sector analysis, and engagement metrics. |

---

## 🚀 Installation

### Prerequisites

- Python 3.8 or higher
- Git
- Conda (recommended) or pip

### Option 1: Using Conda (Recommended)

The easiest way to set up the environment is using the provided `environment.yaml` file:

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/xueqiu-crawler.git
cd xueqiu-crawler

# 2. Create conda environment from yaml file
conda env create -f environment.yaml

# 3. Activate the environment
conda activate xueqiu-crawler

# 4. Install Playwright browser (REQUIRED)
playwright install chromium
```

To update an existing environment:

```bash
conda env update -f environment.yaml --prune
```

To remove the environment:

```bash
conda deactivate
conda env remove -n xueqiu-crawler
```

### Option 2: Using pip (Alternative)

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/xueqiu-crawler.git
cd xueqiu-crawler

# 2. Create virtual environment
python -m venv venv

# 3. Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# 4. Install Python dependencies
pip install -r requirements.txt

# 5. Install Playwright browser (REQUIRED)
playwright install chromium
```

---

## ⚙️ Configuration

### Environment Setup

Create a `.env` file from the template:

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```env
# Required for LLM summarization
FIREWORKS_API_KEY=your-fireworks-api-key-here

# Optional but recommended for better crawl results
XUEQIU_COOKIE=your-xueqiu-cookie-here
```

### Getting Your Fireworks API Key

1. Visit [Fireworks AI](https://app.fireworks.ai/)
2. Sign up or log in
3. Navigate to API Keys section
4. Generate a new API key
5. Copy and paste into your `.env` file

### Getting Your Xueqiu Cookie (Recommended)

Using cookies significantly improves crawl success rate:

1. Open Chrome and navigate to https://xueqiu.com/
2. Press `F12` to open Developer Tools
3. Go to the **Network** tab
4. Refresh the page
5. Click on any request (e.g., the first one)
6. Find the **Cookie** header in Request Headers
7. Copy the entire cookie string
8. Paste into your `.env` file

### Configuration Options

#### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `FIREWORKS_API_KEY` | Fireworks API key for LLM | None |
| `XUEQIU_COOKIE` | Xueqiu session cookie | None |
| `XUEQIU_MAX_POSTS_PER_TAB` | Max posts per tab | 100 |
| `XUEQIU_MAX_CONCURRENT_TABS` | Concurrent tab crawling | 4 |
| `STORAGE_BASE_DIR` | Base storage directory | storage |

#### CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--tabs, -t` | Tabs to crawl (Chinese names or 'all') | all |
| `--max-posts, -m` | Max posts per tab | 50 |
| `--job-name, -j` | Custom job name | auto-generated |
| `--output, -o` | Output directory | storage |
| `--api-key, -k` | Fireworks API key | env var |
| `--no-llm` | Skip LLM summarization | False |
| `--concurrent, -c` | Concurrent tabs | 4 |
| `--log-level, -l` | Logging level | INFO |

---

## 💻 Usage

### Basic Commands

```bash
# Crawl all tabs with default settings
python main.py

# Crawl specific tabs
python main.py --tabs 热门 7x24 资讯

# Limit posts per tab
python main.py --max-posts 30

# Skip LLM summarization (faster, basic analysis only)
python main.py --no-llm

# Custom job name
python main.py --job-name my_analysis_20251207
```

### Advanced Usage

```bash
# Full example with all options
python main.py \
    --tabs all \
    --max-posts 50 \
    --job-name daily_analysis \
    --api-key YOUR_FIREWORKS_API_KEY \
    --output ./data \
    --concurrent 4 \
    --log-level INFO
```

### Utility Commands

```bash
# List all available tabs
python main.py list-tabs

# Show version
python main.py version

# Show help
python main.py --help
```

---

## 📂 Output Structure

```
storage/<job_name>/
├── raw/                          # Raw posts per tab (JSON)
│   ├── posts_热门.json
│   ├── posts_7x24.json
│   ├── posts_视频.json
│   ├── posts_基金.json
│   ├── posts_资讯.json
│   ├── posts_达人.json
│   ├── posts_私募.json
│   └── posts_ETF.json
├── summary/                      # LLM summaries per tab (JSON)
│   ├── summary_热门.json
│   ├── summary_7x24.json
│   └── ...
└── reports/                      # Final reports
    ├── final_report.md           # Markdown report for analysts
    └── report_data.json          # Structured report data
```

---

## 📊 Report Contents

The generated `final_report.md` includes:

| Section | Description |
|---------|-------------|
| **Executive Summary** | Overall market sentiment overview (bullish/bearish/mixed) |
| **Key Discussion Points** | Top themes and topics with representative quotes |
| **Most Discussed Stocks** | Ranked table with sentiment breakdown per stock |
| **Sentiment Distribution** | Positive/Neutral/Negative post counts |
| **Investment Themes & Sectors** | Detailed sector analysis with trend indicators |
| **Representative Discussions** | Verbatim quotes from top-engagement posts |
| **Data Collection Statistics** | Crawl metrics per tab (posts, duration, errors) |
| **Detailed Stock Analysis** | Per-stock sentiment visualization |

### Sample Report Output

```markdown
# Xueqiu Discussion Report — run_20251207_103045

**Generated:** 2025-12-07 10:45:23
**Total Posts Collected:** 423
**Unique Posts:** 398
**Posts Summarized:** 398

## Executive Summary

Overall market sentiment is **bullish** with 45.2% positive, 
32.1% negative, and 22.7% neutral discussions.

## Most Discussed Stocks

| Rank | Symbol | Mentions | Sentiment | Bullish | Bearish | Neutral |
|------|--------|----------|-----------|---------|---------|---------|
| 1 | SH600519 | 47 | 📈 | 32 | 8 | 7 |
| 2 | SZ000001 | 35 | 📉 | 12 | 18 | 5 |
...
```

---

## 📈 Available Tabs

| Tab | Chinese | Description |
|-----|---------|-------------|
| 热门 | Hot | Trending discussions |
| 7x24 | 24/7 | Live news updates (special DOM handling) |
| 视频 | Video | Video content |
| 基金 | Funds | Mutual fund discussions |
| 资讯 | News | Market news |
| 达人 | Experts | Influencer/expert posts |
| 私募 | PE | Private equity discussions |
| ETF | ETF | ETF discussions |

---

## 🔧 Technical Details

### Data Extraction

Each post extracts the following fields:

| Field | Description |
|-------|-------------|
| `text` | Post body text (cleaned) |
| `html` | Raw article HTML |
| `timestamp` | Collection time (ISO format) |
| `tab` | Source tab name |
| `author` | Author username (if available) |
| `symbols` | Detected stock tickers (e.g., SH600519, SZ000001) |
| `like_count` | Number of likes |
| `comment_count` | Number of comments |
| `retweet_count` | Number of retweets |

### LLM Processing

The LLM (Llama-3-8b-instruct via Fireworks AI) performs:

1. **Summarization**: Concise English summary of Chinese posts
2. **Entity Extraction**: Stock tickers, company names
3. **Theme Identification**: Investment themes and market sectors
4. **Sentiment Analysis**: Positive/Neutral/Negative with confidence score

### Data Quality Measures

- **Validation**: Pydantic models ensure required fields
- **Deduplication**: xxhash-based content hashing
- **Incremental Saves**: Data persisted every 30 seconds
- **Error Tracking**: All failures logged and reported

---

## 🐛 Troubleshooting

### Playwright Installation Issues

```bash
# If playwright install fails, try:
pip install playwright
playwright install chromium --with-deps
```

### Cookie Expiration

Xueqiu cookies expire periodically. If you see authentication errors:

1. Clear browser cookies for xueqiu.com
2. Visit the site again
3. Extract fresh cookies using DevTools

### Rate Limiting

If you encounter rate limiting:

- Reduce `--max-posts` value
- Decrease `--concurrent` tabs
- Use `--no-llm` to skip API calls temporarily

### Common Errors

| Error | Solution |
|-------|----------|
| `Playwright not installed` | Run `playwright install chromium` |
| `403 Forbidden` | Update XUEQIU_COOKIE in .env |
| `LLM API Error 429` | Wait and retry, or use `--no-llm` |
| `No posts found` | Check internet connection, try different tab |

---

## 📁 Project Structure

```
xueqiu-crawler/
├── main.py                   # CLI entry point & pipeline orchestration
├── requirements.txt          # Python dependencies (pip)
├── environment.yaml          # Conda environment file (recommended)
├── .env.example              # Environment configuration template
├── README.md                 # This documentation
└── src/
    ├── __init__.py           # Package initialization
    ├── config.py             # Settings, constants, tab mappings
    ├── models.py             # Pydantic data models
    ├── utils.py              # Utility functions (hashing, logging)
    ├── crawler.py            # Playwright-based async crawler
    ├── llm_summarizer.py     # Fireworks AI LLM integration
    ├── storage.py            # JSON storage & incremental saving
    └── report_generator.py   # Markdown report generation
```

---

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

---

## ⚠️ Disclaimer

This tool is for **educational and research purposes only**. Please respect Xueqiu's terms of service and implement appropriate rate limiting when using this crawler. The authors are not responsible for any misuse of this tool.

---

<p align="center">
  <b>Built for Linq 2025 AI & Alt Data Team Coding Test</b>
</p>