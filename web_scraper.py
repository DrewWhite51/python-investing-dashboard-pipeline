#!/usr/bin/env python3
"""
Web scraper for investing news articles.
Scrapes HTML from URLs and saves them with normalized naming convention.
"""

import os
import re
import requests
import database
from datetime import datetime
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

class NewsScraper:
    def __init__(self, output_dir="scraped_html", use_selenium=False):
        self.output_dir = output_dir
        self.use_selenium = use_selenium
        self.driver = None
        self.db_manager = database.DatabaseManager()
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        if use_selenium:
            self.setup_selenium()
    
    def setup_selenium(self):
        """Setup Selenium WebDriver with Chrome options"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Run in background
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            print(f"Error setting up Selenium: {e}")
            print("Make sure ChromeDriver is installed and in PATH")
            raise
    
    def normalize_website_name(self, url):
        """Normalize website name from URL"""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        # Remove www. and common subdomains
        domain = re.sub(r'^(www\.|m\.)', '', domain)
        
        # Replace dots and special characters with underscores
        normalized = re.sub(r'[^a-zA-Z0-9]', '_', domain)
        
        # Remove consecutive underscores and trailing underscores
        normalized = re.sub(r'_+', '_', normalized).strip('_')
        
        return normalized
    
    def scrape_with_requests(self, url):
        """Scrape HTML using requests and BeautifulSoup"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"Error scraping {url} with requests: {e}")
            return None
    
    def scrape_with_selenium(self, url):
        """Scrape HTML using Selenium (for JavaScript-heavy sites)"""
        try:
            self.driver.get(url)
            
            # Wait for page to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Additional wait for dynamic content
            time.sleep(3)
            
            return self.driver.page_source
        except Exception as e:
            print(f"Error scraping {url} with Selenium: {e}")
            return None

    def scrape_url(self, url_data):
        """Scrape a single URL and save HTML - Updated to return URL mapping"""
        url = url_data['url']
        url_id = url_data['db_id']
        
        print(f"Scraping: {url}")
        
        # Get HTML content
        if self.use_selenium:
            html_content = self.scrape_with_selenium(url)
        else:
            html_content = self.scrape_with_requests(url)
        
        if not html_content:
            return None
        
        # Generate filename
        normalized_name = self.normalize_website_name(url)
        date_scraped = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{normalized_name}_{date_scraped}.html"
        filepath = os.path.join(self.output_dir, filename)
        
        # Save HTML to file
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"Saved: {filepath}")
            
            # Return mapping of filepath to URL data
            return {
                'filepath': filepath,
                'url': url,
                'url_id': url_id,
                'filename': filename
            }
        except Exception as e:
            print(f"Error saving file: {e}")
            return None

    def scrape_urls(self, urls):
        """Scrape multiple URLs - Updated to track URL mappings"""
        scraped_files = []
        used_urls_ids = []
        url_mappings = {}  # filename -> url_data mapping
        
        for url_data in urls:
            result = self.scrape_url(url_data)
            if result:
                scraped_files.append(result['filepath'])
                used_urls_ids.append(url_data['db_id'])
                # Store mapping for later use
                url_mappings[result['filename']] = {
                    'url': result['url'],
                    'url_id': result['url_id']
                }
        
        # Save URL mappings to a JSON file for the pipeline to use
        import json
        with open('url_mappings.json', 'w') as f:
            json.dump(url_mappings, f, indent=2)
        
        marked_urls = self.db_manager.mark_urls_used_in_pipeline(used_urls_ids)
        return scraped_files

    def close(self):
        """Clean up resources"""
        if self.driver:
            self.driver.quit()


def main():
    """Example usage"""
    # List of investing news URLs to scrape

    db = database.DatabaseManager()    
    urls = db.get_collected_urls() 
    actual_urls = [url.url for url in urls if url.url]  # Filter out empty URLs
    
    # Initialize scraper (set use_selenium=True for JavaScript-heavy sites)
    scraper = NewsScraper(use_selenium=False)
    
    try:
        # Scrape URLs
        scraped_files = scraper.scrape_urls(actual_urls)
        print(f"\nSuccessfully scraped {len(scraped_files)} files:")
        for file in scraped_files:
            print(f"  - {file}")
    
    finally:
        # Clean up
        scraper.close()


if __name__ == "__main__":
    main()