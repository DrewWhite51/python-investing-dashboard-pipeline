#!/usr/bin/env python3
"""
Main pipeline script to orchestrate the entire news scraping and summarization process.
"""

import os
import sys
import argparse
from datetime import datetime
from dotenv import load_dotenv
# Import our custom modules
from web_scraper import NewsScraper
from html_parser import HTMLParser  
from ai_summarizer import AISummarizer
import database

class NewsPipeline:
    def __init__(self, use_selenium=False, anthropic_api_key=None, model="claude-3-5-sonnet-20241022"):
        self.use_selenium = use_selenium
        self.anthropic_api_key = anthropic_api_key
        self.model = model
        
        # Initialize components
        self.scraper = None
        self.parser = None
        self.summarizer = None
        self.db_manager = database.DatabaseManager()
        
        # Default URLs for financial news
        self.default_urls = [
        ]
    
    def initialize_components(self):
        """Initialize all pipeline components"""
        print("Initializing pipeline components...")
        
        # Initialize scraper
        self.scraper = NewsScraper(use_selenium=self.use_selenium)
        
        # Initialize parser
        self.parser = HTMLParser()
        
        # Initialize summarizer
        try:
            self.summarizer = AISummarizer(
                api_key=self.anthropic_api_key,
                model=self.model
            )
        except ValueError as e:
            print(f"Warning: Could not initialize AI summarizer: {e}")
            self.summarizer = None
        
        print("Components initialized successfully!")
    
    def run_scraping_phase(self, urls=None):
        """Run the web scraping phase"""
        print("\n" + "="*60)
        print("PHASE 1: WEB SCRAPING")
        print("="*60)
        
        urls = [{'url': url.url, 'db_id': url.id} for url in self.db_manager.get_collected_urls() if url.url and url.used_in_pipeline == 0]  # Filter out empty URLs, this should only get the urls not used in the pipeline yet
        try:
            scraped_files = self.scraper.scrape_urls(urls)
            print(f"\nScraping phase completed. {len(scraped_files)} files scraped.")
            return scraped_files
        except Exception as e:
            print(f"Error in scraping phase: {e}")
            return []
    
    def run_parsing_phase(self):
        """Run the HTML parsing phase"""
        print("\n" + "="*60)
        print("PHASE 2: HTML PARSING")
        print("="*60)
        
        try:
            parsed_files = self.parser.parse_all_html_files()
            print(f"\nParsing phase completed. {len(parsed_files)} files parsed.")
            return parsed_files
        except Exception as e:
            print(f"Error in parsing phase: {e}")
            return []
    
    def run_summarization_phase(self):
        """Run the AI summarization phase"""
        print("\n" + "="*60)
        print("PHASE 3: AI SUMMARIZATION")
        print("="*60)
        
        if not self.summarizer:
            print("AI summarizer not available. Skipping summarization phase.")
            print("Please set ANTHROPIC_API_KEY environment variable to enable AI summarization.")
            return []
        
        try:
            summary_files = self.summarizer.batch_process_with_retry()
            print(f"\nSummarization phase completed. {len(summary_files)} files summarized.")
            return summary_files
        except Exception as e:
            print(f"Error in summarization phase: {e}")
            return []
    
    def run_database_translation_phase(self):
        """Run the database translation phase where we move data from summaries to the database"""
        print("\n" + "="*60)
        print("PHASE 4: DATABASE TRANSLATION")
        print("="*60)

    def run_resource_cleanup_phase(self):
        """Run the resource cleanup phase to remove temporary files"""
        print("\n" + "="*60)
        print("PHASE 5: RESOURCE CLEANUP")
        print("="*60)
        
        # try:
        #     self.scraper.cleanup()
        #     self.parser.cleanup()
        #     if self.summarizer:
        #         self.summarizer.cleanup()
        #     print("Resource cleanup completed successfully.")
        # except Exception as e:
        #     print(f"Error during resource cleanup: {e}")
        

    def run_full_pipeline(self, urls=None):
        """Run the complete pipeline"""
        start_time = datetime.now()
        
        print("Starting Investment News Analysis Pipeline")
        print(f"Started at: {start_time}")
        print("="*60)
        
        # Initialize components
        self.initialize_components()
        
        # Phase 1: Scraping
        scraped_files = self.run_scraping_phase(urls)
        
        # Phase 2: Parsing
        parsed_files = self.run_parsing_phase()
        
        # Phase 3: Summarization
        summary_files = self.run_summarization_phase()
        
        # Pipeline summary
        end_time = datetime.now()
        duration = end_time - start_time
        
        print("\n" + "="*60)
        print("PIPELINE SUMMARY")
        print("="*60)
        print(f"Total execution time: {duration}")
        print(f"Files scraped: {len(scraped_files)}")
        print(f"Files parsed: {len(parsed_files)}")
        print(f"Files summarized: {len(summary_files)}")
        
        # Show output directories
        print(f"\nOutput directories:")
        print(f"  - Scraped HTML: ./scraped_html/")
        print(f"  - Cleaned text: ./cleaned_text/")
        print(f"  - AI summaries: ./summaries/")
        
        return {
            'scraped_files': scraped_files,
            'parsed_files': parsed_files,
            'summary_files': summary_files,
            'duration': duration
        }
    
    def cleanup(self):
        """Clean up resources"""
        if self.scraper:
            self.scraper.close()


def main():
    """Main function with command line interface"""
    # Load environment variables from .env file
    load_dotenv()
    
    parser = argparse.ArgumentParser(description='Investment News Analysis Pipeline')
    
    parser.add_argument('--urls', nargs='*', help='URLs to scrape (space-separated)')
    parser.add_argument('--selenium', action='store_true', help='Use Selenium for JavaScript-heavy sites')
    parser.add_argument('--model', default='claude-3-5-sonnet-20241022', help='Claude model to use (default: claude-3-5-sonnet-20241022)')
    parser.add_argument('--api-key', help='Anthropic API key (can also use ANTHROPIC_API_KEY env var)')
    parser.add_argument('--scrape-only', action='store_true', help='Only run scraping phase')
    parser.add_argument('--parse-only', action='store_true', help='Only run parsing phase')
    parser.add_argument('--summarize-only', action='store_true', help='Only run summarization phase')
    
    args = parser.parse_args()
    
    # Initialize pipeline
    pipeline = NewsPipeline(
        use_selenium=args.selenium,
        anthropic_api_key=args.api_key or os.getenv('ANTHROPIC_API_KEY'),
        model=args.model
    )
    
    try:
        if args.scrape_only:
            pipeline.initialize_components()
            pipeline.run_scraping_phase(args.urls)
        elif args.parse_only:
            pipeline.initialize_components()
            pipeline.run_parsing_phase()
        elif args.summarize_only:
            pipeline.initialize_components()
            pipeline.run_summarization_phase()
        else:
            # Run full pipeline
            results = pipeline.run_full_pipeline(args.urls)
            
            # Print final results
            print(f"\nPipeline completed successfully!")
            if results['summary_files']:
                print(f"Check the ./summaries/ directory for AI-generated investment insights.")
    
    except KeyboardInterrupt:
        print("\nPipeline interrupted by user.")
    except Exception as e:
        print(f"Pipeline failed with error: {e}")
        sys.exit(1)
    finally:
        # Clean up
        pipeline.cleanup()


if __name__ == "__main__":
    main()