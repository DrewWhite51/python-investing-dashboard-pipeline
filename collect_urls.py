#!/usr/bin/env python3
"""
Smart URL collector for news articles.
Crawls news homepages and extracts individual article URLs.
"""

import os
import re
import json
import time
import logging
from datetime import datetime
from urllib.parse import urljoin, urlparse, parse_qs
from typing import List, Dict, Set
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class URLCollector:
    def __init__(self, output_file="collected_urls.json", log_file="url_collection.log", use_selenium=False):
        self.output_file = output_file
        self.use_selenium = use_selenium
        self.driver = None
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Common article URL patterns for different news sites
        self.article_patterns = {
            'coindesk.com': [
                r'/\d{4}/\d{2}/\d{2}/',  # Date-based URLs
                r'/news/',
                r'/markets/',
                r'/policy/',
                r'/tech/',
                r'/business/'
            ],
            'marketwatch.com': [
                r'/story/',
                r'/articles/',
                r'/news/'
            ],
            'yahoo.com': [
                r'/news/',
                r'/finance/news/'
            ],
            'cnbc.com': [
                r'/\d{4}/\d{2}/\d{2}/',
                r'/news/',
                r'/investing/'
            ],
            'reuters.com': [
                r'/business/',
                r'/markets/',
                r'/technology/',
                r'/world/'
            ],
            'bloomberg.com': [
                r'/news/',
                r'/opinion/',
                r'/markets/'
            ],
            'wsj.com': [
                r'/articles/',
                r'/news/'
            ],
            'ft.com': [
                r'/content/'
            ],
            'seekingalpha.com': [
                r'/article/',
                r'/news/'
            ],
            'fool.com': [
                r'/investing/',
                r'/retirement/',
                r'/personal-finance/'
            ]
        }
        
        # Selectors to find article links
        self.article_selectors = {
            'coindesk.com': [
                'a[href*="/news/"]',
                'a[href*="/markets/"]',
                'a[href*="/policy/"]',
                'a[href*="/tech/"]',
                'h3 a', 'h4 a', 'h5 a',
                '.articleTextSection a',
                '.listingPage a'
            ],
            'marketwatch.com': [
                'a[href*="/story/"]',
                'a[href*="/articles/"]',
                '.article__headline a',
                '.headline a',
                'h3 a', 'h4 a'
            ],
            'yahoo.com': [
                'a[href*="/news/"]',
                'h3 a', 'h4 a',
                '.js-content-viewer a'
            ],
            'cnbc.com': [
                'a[href*="/2024/"]',
                'a[href*="/news/"]',
                '.InlineArticle-headline a',
                'h3 a', 'h4 a'
            ],
            'reuters.com': [
                'a[href*="/business/"]',
                'a[href*="/markets/"]',
                '.story-title a',
                'h3 a', 'h4 a'
            ],
            'bloomberg.com': [
                'a[href*="/news/"]',
                'a[href*="/opinion/"]',
                '.story-package-module__story a',
                'h3 a', 'h4 a'
            ],
            'default': [
                'a[href*="article"]',
                'a[href*="story"]',
                'a[href*="news"]',
                'a[href*="/2024/"]',
                'a[href*="/2025/"]',
                'h1 a', 'h2 a', 'h3 a', 'h4 a',
                '.article a', '.story a', '.news a'
            ]
        }
        
        if use_selenium:
            self.setup_selenium()
    
    def setup_selenium(self):
        """Setup Selenium WebDriver"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            self.logger.info("Selenium WebDriver initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize Selenium: {e}")
            raise
    
    def get_domain(self, url):
        """Extract domain from URL"""
        return urlparse(url).netloc.lower()
    
    def is_valid_article_url(self, url, base_domain):
        """Check if URL looks like a valid article URL"""
        if not url or url.startswith('#') or url.startswith('javascript:'):
            return False
        
        url_lower = url.lower()
        
        # Skip common non-article URLs
        skip_patterns = [
            'mailto:', 'tel:', 'javascript:', '#',
            'subscribe', 'newsletter', 'login', 'register',
            'contact', 'about', 'privacy', 'terms',
            'search', 'sitemap', 'rss', 'feed',
            'podcast', 'video', 'photo', 'gallery',
            'twitter.com', 'facebook.com', 'linkedin.com',
            'instagram.com', 'youtube.com', 'tiktok.com',
            '/tag/', '/category/', '/author/',
            '/page/', '/archive/', '/index'
        ]
        
        for pattern in skip_patterns:
            if pattern in url_lower:
                return False
        
        # Check domain-specific patterns
        domain_key = None
        for domain in self.article_patterns:
            if domain in base_domain:
                domain_key = domain
                break
        
        if domain_key:
            patterns = self.article_patterns[domain_key]
            for pattern in patterns:
                if re.search(pattern, url):
                    return True
        
        # Fallback: check for common article patterns
        article_indicators = [
            r'/\d{4}/\d{2}/\d{2}/',  # Date patterns
            r'/article/',
            r'/story/',
            r'/news/',
            r'/post/',
            r'/blog/'
        ]
        
        for pattern in article_indicators:
            if re.search(pattern, url):
                return True
        
        return False
    
    def extract_urls_with_requests(self, base_url):
        """Extract URLs using requests and BeautifulSoup"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        try:
            response = requests.get(base_url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            self.logger.error(f"Error fetching {base_url} with requests: {e}")
            return None
    
    def extract_urls_with_selenium(self, base_url):
        """Extract URLs using Selenium"""
        try:
            self.driver.get(base_url)
            
            # Wait for page to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Additional wait for dynamic content
            time.sleep(5)
            
            # Scroll to load more content if needed
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            time.sleep(2)
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
            
            return self.driver.page_source
        except Exception as e:
            self.logger.error(f"Error fetching {base_url} with Selenium: {e}")
            return None
    
    def collect_urls_from_page(self, base_url):
        """Collect article URLs from a single base page"""
        self.logger.info(f"Collecting URLs from: {base_url}")
        
        # Get page content
        if self.use_selenium:
            html_content = self.extract_urls_with_selenium(base_url)
        else:
            html_content = self.extract_urls_with_requests(base_url)
        
        if not html_content:
            return []
        
        # Parse HTML
        soup = BeautifulSoup(html_content, 'html.parser')
        base_domain = self.get_domain(base_url)
        
        # Get appropriate selectors for this domain
        selectors = self.article_selectors.get(base_domain, self.article_selectors['default'])
        for domain_key in self.article_selectors:
            if domain_key != 'default' and domain_key in base_domain:
                selectors = self.article_selectors[domain_key]
                break
        
        # Find all links
        found_urls = set()
        
        for selector in selectors:
            try:
                links = soup.select(selector)
                for link in links:
                    href = link.get('href')
                    if href:
                        # Convert relative URLs to absolute
                        full_url = urljoin(base_url, href)
                        
                        # Clean URL (remove fragments, query params for some cases)
                        parsed = urlparse(full_url)
                        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                        
                        # Validate URL
                        if self.is_valid_article_url(clean_url, base_domain):
                            found_urls.add(clean_url)
            except Exception as e:
                self.logger.warning(f"Error processing selector '{selector}': {e}")
                continue
        
        # Log results
        self.logger.info(f"Found {len(found_urls)} article URLs from {base_url}")
        
        # Log some examples
        if found_urls:
            examples = list(found_urls)[:5]
            self.logger.info(f"Example URLs: {examples}")
        
        return list(found_urls)
    
    def collect_urls_from_multiple_pages(self, base_urls, delay_between_requests=3):
        """Collect URLs from multiple base pages"""
        all_collected_urls = {}
        total_urls = 0
        
        self.logger.info(f"Starting URL collection from {len(base_urls)} base pages")
        
        for i, base_url in enumerate(base_urls, 1):
            self.logger.info(f"Processing {i}/{len(base_urls)}: {base_url}")
            
            try:
                urls = self.collect_urls_from_page(base_url)
                all_collected_urls[base_url] = {
                    'urls': urls,
                    'count': len(urls),
                    'collected_at': datetime.now().isoformat(),
                    'success': True
                }
                total_urls += len(urls)
                
            except Exception as e:
                self.logger.error(f"Failed to collect from {base_url}: {e}")
                all_collected_urls[base_url] = {
                    'urls': [],
                    'count': 0,
                    'collected_at': datetime.now().isoformat(),
                    'success': False,
                    'error': str(e)
                }
            
            # Delay between requests to be respectful
            if i < len(base_urls):
                time.sleep(delay_between_requests)
        
        # Save results
        collection_data = {
            'collection_timestamp': datetime.now().isoformat(),
            'total_base_pages': len(base_urls),
            'total_articles_found': total_urls,
            'results': all_collected_urls
        }
        
        self.save_collection_data(collection_data)
        
        self.logger.info(f"URL collection completed. Total URLs found: {total_urls}")
        return collection_data
    
    def save_collection_data(self, data):
        """Save collection data to JSON file"""
        try:
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self.logger.info(f"Collection data saved to {self.output_file}")
        except Exception as e:
            self.logger.error(f"Error saving collection data: {e}")
    
    def get_flat_url_list(self):
        """Get a flat list of all collected URLs"""
        try:
            with open(self.output_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            flat_urls = []
            for base_url, result in data.get('results', {}).items():
                if result.get('success') and result.get('urls'):
                    flat_urls.extend(result['urls'])
            
            # Remove duplicates while preserving order
            seen = set()
            unique_urls = []
            for url in flat_urls:
                if url not in seen:
                    seen.add(url)
                    unique_urls.append(url)
            
            return unique_urls
            
        except Exception as e:
            self.logger.error(f"Error reading collection data: {e}")
            return []
    
    def close(self):
        """Clean up resources"""
        if self.driver:
            self.driver.quit()


def main():
    """Example usage"""
    # Default financial news base pages
    base_urls = [
        "https://www.coindesk.com/",
        "https://www.marketwatch.com/investing",
        "https://finance.yahoo.com/news",
        "https://www.cnbc.com/investing/",
        "https://www.reuters.com/business/finance/",
        "https://www.bloomberg.com/markets"
    ]
    
    # Initialize collector
    collector = URLCollector(use_selenium=False)
    
    try:
        # Collect URLs
        results = collector.collect_urls_from_multiple_pages(base_urls)
        
        # Get flat list for pipeline
        article_urls = collector.get_flat_url_list()
        
        print(f"\nCollection Summary:")
        print(f"Base pages processed: {results['total_base_pages']}")
        print(f"Total article URLs found: {results['total_articles_found']}")
        print(f"Unique URLs after deduplication: {len(article_urls)}")
        
        if article_urls:
            print(f"\nFirst 10 collected URLs:")
            for i, url in enumerate(article_urls[:10], 1):
                print(f"{i:2d}. {url}")
    
    finally:
        collector.close()


if __name__ == "__main__":
    main()