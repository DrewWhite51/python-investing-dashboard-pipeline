#!/usr/bin/env python3
"""
Smart URL collector for news articles.
Crawls news homepages and extracts individual article URLs.
Now integrated with SQLite database.
"""

import os
import re
import json
import time
import logging
import uuid
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

from database import DatabaseManager

class URLCollector:
    def __init__(self, log_file="url_collection.log", use_selenium=False, db_path="news_pipeline.db"):
        self.use_selenium = use_selenium
        self.driver = None
        self.db = DatabaseManager(db_path)
        
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
    
    def collect_urls_from_source(self, source):
        """Collect article URLs from a single news source"""
        self.logger.info(f"Collecting URLs from: {source.name} ({source.url})")
        
        # Get page content
        if self.use_selenium:
            html_content = self.extract_urls_with_selenium(source.url)
        else:
            html_content = self.extract_urls_with_requests(source.url)
        
        if not html_content:
            return []
        
        # Parse HTML
        soup = BeautifulSoup(html_content, 'html.parser')
        base_domain = self.get_domain(source.url)
        
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
                        full_url = urljoin(source.url, href)
                        
                        # Clean URL (remove fragments, query params for some cases)
                        parsed = urlparse(full_url)
                        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                        
                        # Validate URL
                        if self.is_valid_article_url(clean_url, base_domain):
                            found_urls.add(clean_url)
            except Exception as e:
                self.logger.warning(f"Error processing selector '{selector}': {e}")
                continue
        
        # Convert to list with metadata
        url_data = []
        for url in found_urls:
            url_data.append({
                'source_id': source.id,
                'url': url,
                'domain': self.get_domain(url)
            })
        
        # Log results
        self.logger.info(f"Found {len(url_data)} article URLs from {source.name}")
        
        # Log some examples
        if url_data:
            examples = [item['url'] for item in url_data[:5]]
            self.logger.info(f"Example URLs: {examples}")
        
        return url_data
    
    def collect_urls_from_sources(self, sources, delay_between_requests=3):
        """Collect URLs from multiple news sources and save to database"""
        batch_id = str(uuid.uuid4())
        self.logger.info(f"Starting URL collection batch {batch_id} from {len(sources)} sources")
        
        # Create collection batch in database
        self.db.create_collection_batch(batch_id, len(sources), self.use_selenium)
        
        all_collected_urls = []
        total_urls = 0
        error_message = None
        
        try:
            for i, source in enumerate(sources, 1):
                self.logger.info(f"Processing {i}/{len(sources)}: {source.name}")
                
                try:
                    urls_data = self.collect_urls_from_source(source)
                    
                    if urls_data:
                        # Add URLs to database
                        added_count = self.db.add_collected_urls(urls_data, batch_id)
                        all_collected_urls.extend(urls_data)
                        total_urls += added_count
                        
                        # Update source collection stats
                        self.db.update_collection_stats(source.id, added_count)
                        
                        self.logger.info(f"Added {added_count} URLs from {source.name} to database")
                    else:
                        self.logger.warning(f"No URLs found for {source.name}")
                
                except Exception as e:
                    error_msg = f"Failed to collect from {source.name}: {e}"
                    self.logger.error(error_msg)
                    if not error_message:
                        error_message = error_msg
                
                # Delay between requests to be respectful
                if i < len(sources):
                    time.sleep(delay_between_requests)
        
        except Exception as e:
            error_message = f"Collection batch failed: {e}"
            self.logger.error(error_message)
        
        finally:
            # Complete the batch
            self.db.complete_collection_batch(batch_id, total_urls, error_message)
        
        self.logger.info(f"URL collection batch {batch_id} completed. Total URLs: {total_urls}")
        
        return {
            'batch_id': batch_id,
            'total_urls': total_urls,
            'sources_processed': len(sources),
            'success': error_message is None,
            'error_message': error_message,
            'urls': all_collected_urls
        }
    
    def collect_from_active_sources(self):
        """Collect URLs from all active news sources"""
        sources = self.db.get_news_sources(active_only=True)
        
        if not sources:
            self.logger.warning("No active news sources found")
            return {
                'batch_id': None,
                'total_urls': 0,
                'sources_processed': 0,
                'success': False,
                'error_message': 'No active sources',
                'urls': []
            }
        
        return self.collect_urls_from_sources(sources)
    
    def get_latest_collected_urls(self, limit=1000):
        """Get the most recent collected URLs from database"""
        return self.db.get_latest_collected_urls(limit)
    
    def get_collection_stats(self):
        """Get collection statistics from database"""
        return self.db.get_collection_stats()
    
    def close(self):
        """Clean up resources"""
        if self.driver:
            self.driver.quit()


def main():
    """Example usage"""
    collector = URLCollector(use_selenium=False)
    
    try:
        # Collect URLs from active sources
        results = collector.collect_from_active_sources()
        
        print(f"\nCollection Summary:")
        print(f"Batch ID: {results['batch_id']}")
        print(f"Sources processed: {results['sources_processed']}")
        print(f"Total URLs collected: {results['total_urls']}")
        print(f"Success: {results['success']}")
        
        if results['error_message']:
            print(f"Error: {results['error_message']}")
        
        # Get latest URLs
        latest_urls = collector.get_latest_collected_urls(10)
        if latest_urls:
            print(f"\nFirst 10 latest URLs:")
            for i, url_obj in enumerate(latest_urls[:10], 1):
                print(f"{i:2d}. {url_obj.url}")
        
        # Get stats
        stats = collector.get_collection_stats()
        print(f"\nCollection Statistics:")
        print(f"Total URLs in database: {stats['total_urls']}")
        print(f"Unique domains: {stats['unique_domains']}")
        print(f"URLs used in pipeline: {stats['urls_used']}")
    
    finally:
        collector.close()


if __name__ == "__main__":
    main()