# Enhanced Web Crawler

A Python-based web crawler with robots.txt compliance, rate limiting, and flexible output options. Perfect for ethical web scraping and site analysis.

## Features

- 🤖 **Robots.txt Compliance** - Automatically respects robots.txt rules and crawl delays
- 🛡️ **Rate Limiting** - Configurable delays with per-domain rate limiting
- 🌐 **Multi-domain Support** - Option to follow links to external domains
- 📊 **Multiple Output Formats** - JSON, CSV, or console output
- 🎯 **Pattern Filtering** - Include/exclude URLs with regex patterns
- 📈 **Progress Tracking** - Verbose logging and crawl summaries
- ⚡ **Robust Error Handling** - Handles timeouts, rate limits, and connection errors

## Installation

1. Clone or download the project
2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Quick Start

```bash
# Basic crawl
python main.py --url https://example.com

# CSV output with verbose logging
python main.py --url https://example.com --output data.csv --format csv --verbose

# Deep crawl with custom delay
python main.py --url https://example.com --depth 5 --delay 2 --output deep_crawl.json
```

## Command Line Options

### Required
- `--url URL` - Starting URL to scrape

### Crawling Behavior
- `--depth N` - Maximum crawl depth (default: 3)
- `--delay N` - Minimum delay between requests in seconds (default: 1.0)
- `--allow-exit` - Allow following links to external domains
- `--external-links-depth N` - Maximum external domains to follow (requires --allow-exit)

### Robots.txt & Compliance
- `--no-robots` - Disable robots.txt compliance (not recommended)
- `--bot-name NAME` - User-agent name for robots.txt (default: *)
- `--user-agent AGENT` - Custom User-Agent string

### Output Options
- `--output FILE`, `-o FILE` - Output file name/path (default: output.json)
- `--format FORMAT` - Output format: json, csv, or print (default: json)

### Filtering
- `--exclude PATTERN [PATTERN ...]` - URL patterns to exclude (supports wildcards)
- `--include PATTERN [PATTERN ...]` - Only include URLs matching these patterns

### Other
- `--verbose`, `-v` - Enable verbose logging

## Usage Examples

### Basic Website Crawl
```bash
python main.py --url https://example.com
```

### Blog Analysis
```bash
python main.py --url https://blog.example.com \
  --include "*/posts/*" "*/articles/*" \
  --exclude "*/admin/*" \
  --format csv --output blog_analysis.csv
```

### Multi-domain Research
```bash
python main.py --url https://start-site.com \
  --allow-exit --external-links-depth 3 \
  --depth 2 --delay 1.5 \
  --verbose
```

### Respectful Deep Crawl
```bash
python main.py --url https://documentation-site.com \
  --depth 4 --delay 2 \
  --bot-name "ResearchBot" \
  --verbose
```

### Quick Site Overview
```bash
python main.py --url https://company.com --depth 1 --format print
```

## Output Formats

### JSON Output
Complete structured data including:
- URL, title, meta description/keywords
- All headings (H1, H2, H3)
- Internal links and images
- Text length and timestamps
- HTTP status codes

### CSV Output
Flattened data perfect for analysis:
- Basic page info (URL, title, description)
- Metrics (text length, link count, heading counts)
- First 3 H1 headings as pipe-separated text

### Print Output
Human-readable console output with key metrics

## Robots.txt Compliance

The crawler automatically:
- Downloads and parses robots.txt for each domain
- Respects `Disallow` directives for your specified user-agent
- Honors `Crawl-delay` directives (uses the higher of robots.txt delay or your --delay setting)
- Caches robots.txt to avoid repeated requests

### User-Agent Matching
- Use `--bot-name "*"` to match wildcard rules (default)
- Use `--bot-name "Googlebot"` to match specific bot rules
- Use `--no-robots` to disable compliance entirely (use responsibly!)

## Rate Limiting & Ethics

The crawler implements several ethical scraping practices:
- **Per-domain rate limiting** - Separate delays for each domain
- **Automatic backoff** - Extra delays when receiving 429 (Too Many Requests)
- **Robots.txt compliance** - Respects website owner preferences
- **Content-type checking** - Only processes HTML content
- **Reasonable defaults** - 1 second delay, depth limit of 3

## Troubleshooting

### No Data Saved
- Check if the start URL is accessible
- Use `--verbose` to see what's happening
- Verify robots.txt isn't blocking your crawl

### Rate Limited
- Increase `--delay` value
- Some sites have strict rate limits in robots.txt
- The crawler automatically handles 429 responses

### External Links Not Followed
- Use `--allow-exit` to enable external domain crawling
- Set `--external-links-depth N` to limit how many external domains to follow

### No Links Found
- Check if your `--include`/`--exclude` patterns are too restrictive
- Verify the site actually has internal links
- Try increasing `--depth`

## Example Output Structure

### JSON
```json
{
  "url": "https://example.com/page",
  "domain": "example.com",
  "title": "Page Title",
  "meta_description": "Page description",
  "headings": {
    "h1": ["Main Heading"],
    "h2": ["Sub Heading 1", "Sub Heading 2"],
    "h3": ["Detail 1", "Detail 2"]
  },
  "links": ["https://example.com/link1", "https://example.com/link2"],
  "images": [
    {"src": "https://example.com/image.jpg", "alt": "Image description"}
  ],
  "text_length": 1500,
  "status_code": 200,
  "timestamp": "2025-08-30 15:30:00"
}
```

## Dependencies

- **requests** - HTTP library for making web requests
- **beautifulsoup4** - HTML parsing and data extraction

## Note
Code is fully written by me.\
Comments were generated with the help of AI (Claude 4 Sonnet).