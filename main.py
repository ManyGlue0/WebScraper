import re
import csv
import sys
import json
import time
import fnmatch
import logging
import argparse
import requests

from collections import deque
from bs4 import BeautifulSoup
from typing import Set, Dict, List, Optional
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse, urljoin, urlunparse


class WebScraper:
    def __init__(self, start_url: str, allow_exit: bool = False, 
                 external_links_depth: int = 0, max_depth: int = 3,
                 delay: float = 1.0, output_format: str = 'json',
                 verbose: bool = False, headers: Optional[Dict] = None,
                 exclude_patterns: Optional[List[str]] = None,
                 include_patterns: Optional[List[str]] = None,
                 respect_robots: bool = True, user_agent: str = '*'):
        
        # Core configuration
        self.start_url = start_url
        self.allow_exit = allow_exit
        self.external_links_depth = external_links_depth
        self.max_depth = max_depth
        self.delay = delay
        self.output_format = output_format
        self.verbose = verbose
        self.respect_robots = respect_robots
        self.user_agent = user_agent
        
        # Default headers if none provided
        self.headers = headers or {
            'User-Agent': 'Mozilla/5.0 (compatible; WebScraper/1.0; +http://example.com/bot)'
        }
        
        # Compile regex patterns for URL filtering
        self.exclude_patterns = [re.compile(p) for p in (exclude_patterns or [])]
        self.include_patterns = [re.compile(p) for p in (include_patterns or [])]
        
        # Domain tracking
        self.start_domain = urlparse(start_url).netloc
        self.visited_urls: Set[str] = set()
        self.scraped_data: List[Dict] = []
        self.max_external_hops = 0
        self.current_domains: Set[str] = {self.start_domain}
        
        # Robots.txt caching and rate limiting
        self.robots_cache: Dict[str, RobotFileParser] = {}
        self.domain_delays: Dict[str, float] = {}
        
        # Logging setup
        log_level = logging.DEBUG if verbose else logging.INFO
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)


    def get_robots_parser(self, domain: str) -> Optional[RobotFileParser]:
        """Get or create robots.txt parser for a domain"""
        if not self.respect_robots:
            return None
            
        if domain in self.robots_cache:
            return self.robots_cache[domain]
        
        try:
            # Build robots.txt URL
            parsed_start = urlparse(self.start_url)
            scheme = parsed_start.scheme or "https"
            robots_url = f"{scheme}://{domain}/robots.txt"
            rp = RobotFileParser()
            rp.set_url(robots_url)
            
            # Fetch and parse robots.txt
            response = requests.get(robots_url, timeout=5, headers=self.headers, allow_redirects=True)
            if response.status_code == 200:
                rp.parse(response.text.splitlines())
                self.robots_cache[domain] = rp
                
                # Extract crawl-delay directive
                crawl_delay = rp.crawl_delay(self.user_agent)
                if crawl_delay:
                    self.domain_delays[domain] = float(crawl_delay)
                    self.logger.info(f"Found crawl-delay of {crawl_delay}s for {domain}")
                
                self.logger.info(f"Loaded robots.txt for {domain}")
                return rp
            else:
                self.logger.debug(f"No robots.txt found for {domain} (HTTP {response.status_code})")
                # Cache negative result to avoid repeated requests
                self.robots_cache[domain] = None
                return None
                
        except Exception as e:
            self.logger.debug(f"Error loading robots.txt for {domain}: {e}")
            self.robots_cache[domain] = None
            return None


    def can_fetch(self, url: str) -> bool:
        """Check robots.txt permissions for URL"""
        if not self.respect_robots:
            return True
        
        domain = urlparse(url).netloc
        rp = self.get_robots_parser(domain)
        
        if rp is None:
            return True  # No robots.txt or error loading it
        
        can_fetch = rp.can_fetch(self.user_agent, url)
        if not can_fetch:
            self.logger.debug(f"Robots.txt disallows: {url}")
        
        return can_fetch


    def get_crawl_delay(self, url: str) -> float:
        """Get appropriate delay for this domain"""
        domain = urlparse(url).netloc
        
        # Use domain-specific delay from robots.txt if available
        if domain in self.domain_delays:
            return max(self.delay, self.domain_delays[domain])
        
        return self.delay


    def is_valid_url(self, url: str) -> bool:
        """Check URL against robots.txt and filter patterns"""
        # Check robots.txt compliance first
        if not self.can_fetch(url):
            return False
        
        # Apply exclude patterns
        if self.exclude_patterns:
            for pattern in self.exclude_patterns:
                if pattern.search(url):
                    self.logger.debug(f"URL excluded by pattern: {url}")
                    return False
        
        # Apply include patterns (if specified)
        if self.include_patterns:
            for pattern in self.include_patterns:
                if pattern.search(url):
                    return True
            return False
        
        return True


    def is_same_domain(self, url: str) -> bool:
        """Check domain restrictions and external link limits"""
        domain = urlparse(url).netloc
        
        if domain == self.start_domain:
            return True
        
        if self.allow_exit:
            if domain not in self.current_domains:
                # Check if we can add another external domain
                if self.max_external_hops < self.external_links_depth:
                    self.max_external_hops += 1
                    self.current_domains.add(domain)
                    self.logger.info(f"Following to external domain: {domain} ({self.max_external_hops}/{self.external_links_depth})")
                    return True
                else:
                    self.logger.debug(f"Max external hops reached, skipping: {domain}")
                    return False
            return True
        
        return False


    def extract_data(self, soup: BeautifulSoup, url: str) -> Dict:
        """Extract structured data from HTML page"""
        data = {
            'url': url,
            'domain': urlparse(url).netloc,
            'title': soup.title.string.strip() if soup.title and soup.title.string else '',
            'meta_description': '',
            'meta_keywords': '',
            'headings': {
                'h1': [],
                'h2': [],
                'h3': []
            },
            'links': [],
            'images': [],
            'text_length': len(soup.get_text().strip()),
            'status_code': None,  # Set by scrape_url
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # Extract meta tags
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc:
            data['meta_description'] = meta_desc.get('content', '').strip()
        
        meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
        if meta_keywords:
            data['meta_keywords'] = meta_keywords.get('content', '').strip()
        
        # Extract headings (up to 5 of each type)
        for level in ['h1', 'h2', 'h3']:
            headings = soup.find_all(level)
            data['headings'][level] = [h.get_text().strip() for h in headings[:5] if h.get_text().strip()]
        
        # Extract internal links only
        links = soup.find_all('a', href=True)
        for link in links[:50]:
            absolute_url = urljoin(url, link['href'])
            if self.is_same_domain(absolute_url):
                data['links'].append(absolute_url)
        
        # Extract images with alt text
        images = soup.find_all('img', src=True)
        for img in images[:20]:
            img_data = {
                'src': urljoin(url, img['src']),
                'alt': img.get('alt', '').strip()
            }
            data['images'].append(img_data)
        
        return data


    def scrape_url(self, url: str) -> Optional[Dict]:
        """Scrape single URL and return extracted data"""
        try:
            self.logger.info(f"Scraping: {url}")
            response = requests.get(url, headers=self.headers, timeout=15, allow_redirects=True)
            
            # Handle rate limiting
            if response.status_code == 429:
                self.logger.warning(f"Rate limited on {url}, waiting extra time...")
                time.sleep(self.delay * 3)
                return None
            
            response.raise_for_status()
            
            # Verify HTML content
            content_type = response.headers.get('content-type', '').lower()
            if ('text/html' not in content_type) and ('application/xhtml+xml' not in content_type):
                self.logger.debug(f"Skipping non-HTML content: {url} ({content_type})")
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            data = self.extract_data(soup, url)
            data['status_code'] = response.status_code
            
            return data
            
        except requests.exceptions.Timeout:
            self.logger.warning(f"Timeout scraping {url}")
            return None
        except requests.exceptions.ConnectionError:
            self.logger.warning(f"Connection error for {url}")
            return None
        except requests.RequestException as e:
            self.logger.error(f"Error scraping {url}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error scraping {url}: {e}")
            return None


    def get_links_from_page(self, url: str) -> List[str]:
        """Extract and filter links from a page for crawling"""
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            # Check content type
            content_type = response.headers.get('content-type', '').lower()
            if ('text/html' not in content_type) and ('application/xhtml+xml' not in content_type):
                return []
            
            soup = BeautifulSoup(response.content, 'html.parser')
            links = []
            
            for link in soup.find_all('a', href=True):
                absolute_url = urljoin(url, link['href'])
                # Clean URL (remove fragments and query params for deduplication)
                parsed = urlparse(absolute_url)
                clean_url = urlunparse(parsed._replace(fragment='', query=''))
                
                if (clean_url and 
                    clean_url != url and  # Skip self-links
                    self.is_valid_url(clean_url) and
                    self.is_same_domain(clean_url)):
                    links.append(clean_url)
            
            # Deduplicate while preserving order
            seen = set()
            unique_links = []
            for link in links:
                if link not in seen:
                    seen.add(link)
                    unique_links.append(link)
            
            return unique_links
            
        except requests.RequestException as e:
            self.logger.error(f"Error getting links from {url}: {e}")
            return []


    def crawl(self):
        """Main BFS crawling loop"""
        try:
            # Test start URL accessibility
            self.logger.info(f"Testing accessibility of start URL: {self.start_url}")
            try:
                test_response = requests.head(self.start_url, headers=self.headers, timeout=10, allow_redirects=True)
                status = test_response.status_code
                if status >= 400 or status == 405:
                    raise Exception("HEAD not reliable")
            except Exception:
                r = requests.get(self.start_url, headers=self.headers, timeout=10, stream=True, allow_redirects=True)
                status = r.status_code
                r.close()
            self.logger.info(f"Start URL returned status: {status}")
            
            # Check robots.txt for start URL
            if not self.can_fetch(self.start_url):
                self.logger.warning(f"Robots.txt disallows crawling start URL: {self.start_url}")
                if self.respect_robots:
                    self.logger.error("Cannot proceed due to robots.txt restrictions. Use --no-robots to override (not recommended).")
                    return
                    
        except Exception as e:
            self.logger.warning(f"Could not test start URL accessibility: {e}")
        
        queue = deque([(self.start_url, 0)])  # (url, depth)
        last_request_time = {}  # Per-domain rate limiting
        
        self.logger.info(f"Starting crawl from: {self.start_url}")
        self.logger.info(f"Robots.txt compliance: {'Enabled' if self.respect_robots else 'Disabled'}")
        
        while queue:
            current_url, depth = queue.popleft()
            
            # Skip already visited URLs
            if current_url in self.visited_urls:
                continue
            
            # Check depth limit
            if depth > self.max_depth:
                self.logger.debug(f"Max depth reached for: {current_url}")
                continue
            
            # Check domain restrictions
            if not self.is_same_domain(current_url):
                continue
            
            self.visited_urls.add(current_url)
            
            # Per-domain rate limiting
            domain = urlparse(current_url).netloc
            crawl_delay = self.get_crawl_delay(current_url)
            
            if domain in last_request_time:
                time_since_last = time.time() - last_request_time[domain]
                if time_since_last < crawl_delay:
                    sleep_time = crawl_delay - time_since_last
                    self.logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s for {domain}")
                    time.sleep(sleep_time)
            
            last_request_time[domain] = time.time()
            
            # Scrape the current page
            data = self.scrape_url(current_url)
            if data:
                self.scraped_data.append(data)
                
                # Get links for next depth level
                if depth < self.max_depth:
                    links = self.get_links_from_page(current_url)
                    self.logger.debug(f"Found {len(links)} valid links on {current_url}")
                    
                    for link in links:
                        if link not in self.visited_urls:
                            queue.append((link, depth + 1))
            
            # Progress updates
            if len(self.scraped_data) % 10 == 0 and len(self.scraped_data) > 0:
                self.logger.info(f"Progress: {len(self.scraped_data)} pages scraped, {len(queue)} in queue")
        
        self.logger.info(f"Crawling complete. Scraped {len(self.scraped_data)} pages from {len(self.visited_urls)} URLs")


    def save_results(self, output_file: Optional[str] = None, output_format: Optional[str] = None):
        """Save scraped data in specified format"""
        if not self.scraped_data:
            self.logger.warning("No data to save")
            return
        
        try:
            if output_file:
                self.logger.info(f"Attempting to save {len(self.scraped_data)} items to {output_file}")
                
                # Use provided format or fall back to instance format
                fmt = output_format or self.output_format
                
                if fmt == 'json':
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(self.scraped_data, f, indent=2, ensure_ascii=False)
                    self.logger.info(f"Successfully saved JSON data to {output_file}")
                
                elif fmt == 'csv':
                    # Flatten nested data for CSV format
                    flattened_data = []
                    for item in self.scraped_data:
                        flat_item = {
                            'url': item['url'],
                            'domain': item['domain'],
                            'title': item['title'],
                            'meta_description': item['meta_description'],
                            'meta_keywords': item['meta_keywords'],
                            'text_length': item['text_length'],
                            'status_code': item.get('status_code', ''),
                            'timestamp': item['timestamp'],
                            'num_links': len(item['links']),
                            'num_images': len(item['images']),
                            'h1_count': len(item['headings']['h1']),
                            'h2_count': len(item['headings']['h2']),
                            'h3_count': len(item['headings']['h3']),
                            'h1_text': ' | '.join(item['headings']['h1'][:3]),  # First 3 h1s
                        }
                        flattened_data.append(flat_item)
                    
                    if flattened_data:
                        with open(output_file, 'w', newline='', encoding='utf-8') as f:
                            writer = csv.DictWriter(f, fieldnames=flattened_data[0].keys())
                            writer.writeheader()
                            writer.writerows(flattened_data)
                        self.logger.info(f"Successfully saved CSV data to {output_file}")
                    else:
                        self.logger.warning("No flattened data to save to CSV")
                
                else:  # 'print' format with output file
                    # Save as plain text
                    with open(output_file, 'w', encoding='utf-8') as f:
                        for item in self.scraped_data:
                            f.write(f"URL: {item['url']}\n")
                            f.write(f"Title: {item['title']}\n")
                            f.write(f"Description: {item['meta_description']}\n")
                            f.write(f"Text length: {item['text_length']}\n")
                            f.write(f"Links found: {len(item['links'])}\n")
                            f.write(f"Status: {item.get('status_code', 'Unknown')}\n")
                            f.write("-" * 50 + "\n\n")
                    self.logger.info(f"Successfully saved text data to {output_file}")
            
            else:
                # Output to stdout
                if self.output_format == 'json':
                    print(json.dumps(self.scraped_data, indent=2, ensure_ascii=False))
                else:
                    for item in self.scraped_data:
                        print(f"\nURL: {item['url']}")
                        print(f"Title: {item['title']}")
                        print(f"Description: {item['meta_description']}")
                        print(f"Text length: {item['text_length']}")
                        print(f"Links found: {len(item['links'])}")
                        print(f"Status: {item.get('status_code', 'Unknown')}")
                        print("-" * 50)
        
        except Exception as e:
            self.logger.error(f"Error saving results: {e}")
            raise


    def print_summary(self):
        """Print crawling statistics"""
        if not self.scraped_data:
            return
        
        domains_scraped = set(item['domain'] for item in self.scraped_data)
        total_links = sum(len(item['links']) for item in self.scraped_data)
        total_images = sum(len(item['images']) for item in self.scraped_data)
        
        print(f"\n{'='*50}")
        print("CRAWL SUMMARY")
        print(f"{'='*50}")
        print(f"Pages scraped: {len(self.scraped_data)}")
        print(f"URLs visited: {len(self.visited_urls)}")
        print(f"Domains: {', '.join(domains_scraped)}")
        print(f"Total links found: {total_links}")
        print(f"Total images found: {total_images}")
        print(f"Robots.txt compliance: {'Enabled' if self.respect_robots else 'Disabled'}")
        
        if self.domain_delays:
            print(f"Custom crawl delays: {self.domain_delays}")


def main():
    parser = argparse.ArgumentParser(
        description='Python Web Scraper',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Core arguments
    parser.add_argument('--url', required=True, help='Starting URL to scrape')
    
    # Navigation options
    parser.add_argument('--allow-exit', action='store_true',
                       help='Allow following links to external domains')
    parser.add_argument('--external-links-depth', type=int, default=0,
                       help='Maximum number of external domains to follow (requires --allow-exit)')
    
    # Crawling behavior
    parser.add_argument('--depth', type=int, default=3,
                       help='Maximum crawl depth (default: 3)')
    parser.add_argument('--delay', type=float, default=1.0,
                       help='Minimum delay between requests in seconds (default: 1.0)')
    
    # Robots.txt compliance
    parser.add_argument('--no-robots', action='store_true',
                       help='Disable robots.txt compliance (not recommended)')
    parser.add_argument('--bot-name', default='*',
                       help='User-agent name for robots.txt compliance (default: *)')
    
    # Output configuration
    parser.add_argument('--output', '-o', help='Output file path', default='output.json')
    parser.add_argument('--format', choices=['json', 'csv', 'print'], default='json',
                       help='Output format (default: json)')
    
    # URL filtering
    parser.add_argument('--exclude', nargs='*', default=[],
                       help='URL patterns to exclude (supports wildcards)')
    parser.add_argument('--include', nargs='*', default=[],
                       help='Only include URLs matching these patterns')
    
    # Miscellaneous
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    parser.add_argument('--user-agent', help='Custom User-Agent string')
    
    args = parser.parse_args()
    
    # Argument validation
    if args.external_links_depth > 0 and not args.allow_exit:
        parser.error("--external-links-depth requires --allow-exit to be set")

    if args.format == "print":
        args.output = None
    
    # Setup custom headers
    headers = None
    if args.user_agent:
        headers = {'User-Agent': args.user_agent}
    
    # Convert wildcard patterns to regex
    def wildcard_to_regex(p): 
        return re.compile(fnmatch.translate(p), re.IGNORECASE)
    exclude_patterns = [wildcard_to_regex(p) for p in args.exclude]
    include_patterns = [wildcard_to_regex(p) for p in args.include]
    
    # Initialize scraper
    scraper = WebScraper(
        start_url=args.url,
        allow_exit=args.allow_exit,
        external_links_depth=args.external_links_depth,
        max_depth=args.depth,
        delay=args.delay,
        output_format=args.format,
        verbose=args.verbose,
        headers=headers,
        exclude_patterns=exclude_patterns,
        include_patterns=include_patterns,
        respect_robots=not args.no_robots,
        user_agent=args.bot_name
    )
    
    try:
        # Run the crawl
        scraper.crawl()
        
        # Show summary if requested
        if args.verbose or args.format == 'print':
            scraper.print_summary()
        
        # Save results
        if scraper.scraped_data:
            scraper.save_results(args.output)
        else:
            print("No data was scraped. Check your URL and settings.")
            # Debug information
            print(f"Visited URLs: {len(scraper.visited_urls)}")
            print(f"Start URL accessible: {scraper.can_fetch(args.url) if scraper.respect_robots else 'Not checked'}")
            if scraper.visited_urls:
                print(f"First few visited URLs: {list(scraper.visited_urls)[:5]}")
        
    except KeyboardInterrupt:
        print("\nCrawling interrupted by user")
        if scraper.scraped_data:
            print(f"Partial results: {len(scraper.scraped_data)} pages scraped")
            save = input("Save partial results? (y/n): ").strip().lower()
            if save == 'y':
                # Interactive save options
                filename = input(f"File name (default: {args.output}): ").strip()
                if not filename:
                    filename = args.output or f"partial-{int(time.time())}.json"

                fmt = input(f"File format [json/csv] (default: {args.format}): ").strip().lower()
                if fmt not in ("json", "csv"):
                    fmt = args.format if args.format in ("json", "csv") else "json"

                args.output, args.format = filename, fmt
                scraper.save_results(args.output, args.format)
                scraper.print_summary()
                print(f"Saved partial results to {args.output}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()