#!/usr/bin/env python3
"""
HTML parser for scraped news articles.
Cleans HTML and extracts raw text content.
"""

import os
import re
import glob
from bs4 import BeautifulSoup, Comment
from pathlib import Path

class HTMLParser:
    def __init__(self, input_dir="scraped_html", output_dir="cleaned_text"):
        self.input_dir = input_dir
        self.output_dir = output_dir
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
    
    def remove_unwanted_elements(self, soup):
        """Remove unwanted HTML elements"""
        # List of tags to remove completely
        unwanted_tags = [
            'script', 'style', 'nav', 'header', 'footer', 'aside',
            'advertisement', 'ads', 'sidebar', 'menu', 'form',
            'button', 'input', 'select', 'textarea', 'iframe',
            'embed', 'object', 'applet', 'noscript'
        ]
        
        # Remove unwanted tags
        for tag in unwanted_tags:
            for element in soup.find_all(tag):
                element.decompose()
        
        # Remove elements with common ad/navigation classes and IDs
        unwanted_patterns = [
            'ad', 'advertisement', 'banner', 'popup', 'modal',
            'nav', 'navigation', 'menu', 'sidebar', 'footer',
            'header', 'cookie', 'subscribe', 'newsletter',
            'social', 'share', 'comment', 'related', 'recommended'
        ]
        
        for pattern in unwanted_patterns:
            # Remove by class
            for element in soup.find_all(class_=re.compile(pattern, re.I)):
                element.decompose()
            
            # Remove by ID
            for element in soup.find_all(id=re.compile(pattern, re.I)):
                element.decompose()
        
        # Remove HTML comments
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()
        
        return soup
    
    def extract_main_content(self, soup):
        """Extract main article content"""
        # Priority selectors for main content
        content_selectors = [
            'article',
            '[role="main"]',
            '.article-content',
            '.post-content', 
            '.entry-content',
            '.content-body',
            '.story-body',
            '.article-body',
            '.main-content',
            '#main-content',
            '.content',
            '#content'
        ]
        
        main_content = None
        
        # Try each selector in order of priority
        for selector in content_selectors:
            elements = soup.select(selector)
            if elements:
                main_content = elements[0]
                break
        
        # If no main content found, use body
        if not main_content:
            main_content = soup.find('body') or soup
        
        return main_content
    
    def extract_metadata(self, soup):
        """Extract article metadata"""
        metadata = {}
        
        # Title
        title_tag = soup.find('title')
        if title_tag:
            metadata['title'] = title_tag.get_text().strip()
        
        # Meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc:
            metadata['description'] = meta_desc.get('content', '').strip()
        
        # Open Graph title and description
        og_title = soup.find('meta', attrs={'property': 'og:title'})
        if og_title:
            metadata['og_title'] = og_title.get('content', '').strip()
        
        og_desc = soup.find('meta', attrs={'property': 'og:description'})
        if og_desc:
            metadata['og_description'] = og_desc.get('content', '').strip()
        
        # Article published time
        time_selectors = [
            'time[datetime]',
            '.published-date',
            '.article-date',
            '.post-date',
            '[class*="date"]'
        ]
        
        for selector in time_selectors:
            time_element = soup.select_one(selector)
            if time_element:
                metadata['published_time'] = time_element.get_text().strip()
                break
        
        return metadata
    
    def clean_text(self, text):
        """Clean extracted text"""
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove multiple consecutive newlines
        text = re.sub(r'\n\s*\n', '\n\n', text)
        
        # Remove leading/trailing whitespace
        text = text.strip()
        
        return text
    
    def parse_html_file(self, html_filepath):
        """Parse a single HTML file and extract clean text"""
        print(f"Parsing: {html_filepath}")
        
        try:
            # Read HTML file
            with open(html_filepath, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            # Parse with BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Extract metadata
            metadata = self.extract_metadata(soup)
            
            # Remove unwanted elements
            soup = self.remove_unwanted_elements(soup)
            
            # Extract main content
            main_content = self.extract_main_content(soup)
            
            # Get text content
            text_content = main_content.get_text(separator='\n')
            
            # Clean text
            clean_text = self.clean_text(text_content)
            
            # Generate output filename
            input_filename = Path(html_filepath).stem
            output_filename = f"clean_{input_filename}.txt"
            output_filepath = os.path.join(self.output_dir, output_filename)
            
            # Prepare content to save
            content_to_save = []
            
            # Add metadata if available
            if metadata.get('title'):
                content_to_save.append(f"TITLE: {metadata['title']}")
            
            if metadata.get('description') or metadata.get('og_description'):
                desc = metadata.get('og_description') or metadata.get('description')
                content_to_save.append(f"DESCRIPTION: {desc}")
            
            if metadata.get('published_time'):
                content_to_save.append(f"PUBLISHED: {metadata['published_time']}")
            
            if content_to_save:
                content_to_save.append("="*80)
            
            content_to_save.append(clean_text)
            
            # Save clean text to file
            with open(output_filepath, 'w', encoding='utf-8') as f:
                f.write('\n'.join(content_to_save))
            
            print(f"Saved clean text: {output_filepath}")
            return output_filepath
            
        except Exception as e:
            print(f"Error parsing {html_filepath}: {e}")
            return None
    
    def parse_all_html_files(self):
        """Parse all HTML files in the input directory"""
        # Find all HTML files
        html_pattern = os.path.join(self.input_dir, "*.html")
        html_files = glob.glob(html_pattern)
        
        if not html_files:
            print(f"No HTML files found in {self.input_dir}")
            return []
        
        print(f"Found {len(html_files)} HTML files to parse")
        
        parsed_files = []
        for html_file in html_files:
            output_file = self.parse_html_file(html_file)
            if output_file:
                parsed_files.append(output_file)
        
        return parsed_files


def main():
    """Example usage"""
    parser = HTMLParser()
    
    # Parse all HTML files
    parsed_files = parser.parse_all_html_files()
    
    print(f"\nSuccessfully parsed {len(parsed_files)} files:")
    for file in parsed_files:
        print(f"  - {file}")


if __name__ == "__main__":
    main()