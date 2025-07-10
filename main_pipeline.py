#!/usr/bin/env python3
"""
Main pipeline script to orchestrate the entire news scraping and summarization process.
"""

import os
import sys
import glob
import argparse
from datetime import datetime
from dotenv import load_dotenv
# Import our custom modules
from web_scraper import NewsScraper
from html_parser import HTMLParser  
from ai_summarizer import OllamaAISummarizer as AISummarizer
from collect_urls import URLCollector
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
        self.collector = None
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

        # Initialize collector
        self.collector = URLCollector()
        
        # Initialize summarizer
        try:
            self.summarizer = AISummarizer(model="llama3.1:8b")
        except ValueError as e:
            print(f"Warning: Could not initialize AI summarizer: {e}")
            self.summarizer = None
        
        print("Components initialized successfully!")
    
    def run_scraping_phase(self, urls=None):
        """Run the web scraping phase"""
        print("\n" + "="*60)
        print("PHASE 3: WEB SCRAPING")
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
        print("PHASE 4: HTML PARSING")
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
        print("PHASE 5: AI SUMMARIZATION")
        print("="*60)
        
        if not self.summarizer:
            print("AI summarizer not available. Skipping summarization phase.")
            return []
        
        try:
            summary_files = self.summarizer.batch_process_with_retry()
            print(f"\nSummarization phase completed. {len(summary_files)} files summarized.")
            return summary_files
        except Exception as e:
            print(f"Error in summarization phase: {e}")
            return []
    
    def run_database_transformation_phase(self):
        """Run the database translation phase where we move data from summaries to the database"""
        print("\n" + "="*60)
        print("PHASE 6: DATABASE TRANSLATION")
        print("="*60)
        
        import json
        import glob
        import os
        from database import DatabaseManager
        
        try:
            # Initialize database manager
            db_manager = DatabaseManager()
            
            # Get count before translation
            initial_count = db_manager.get_summaries_count()
            print(f"Initial summaries in database: {initial_count}")
            
            # Find all summary JSON files
            summaries_dir = "summaries"
            json_pattern = os.path.join(summaries_dir, "summary_*.json")
            json_files = glob.glob(json_pattern)
            
            print(f"Found {len(json_files)} summary files to process")
            
            if not json_files:
                print("No summary files found in summaries directory")
                return
            
            # Process each summary file
            success_count = 0
            error_count = 0
            skipped_count = 0
            
            for json_file in json_files:
                try:
                    filename = os.path.basename(json_file)
                    print(f"Processing: {filename}")
                    
                    with open(json_file, 'r', encoding='utf-8') as f:
                        summary_data = json.load(f)
                    
                    # Check if already exists
                    source_file = summary_data.get('source_file', filename)
                    if db_manager.check_summary_exists(source_file):
                        print(f"  ⏭️  Already exists in database, skipping")
                        skipped_count += 1
                        continue
                    
                    # Validate required fields
                    if 'parsed_summary' not in summary_data:
                        print(f"  ⚠️  Skipping - missing parsed_summary")
                        error_count += 1
                        continue
                    
                    # Add to database
                    if db_manager.add_article_summary(summary_data):
                        print(f"  ✅ Successfully added to database")
                        success_count += 1
                    else:
                        print(f"  ❌ Failed to add to database")
                        error_count += 1
                        
                except json.JSONDecodeError as e:
                    print(f"  ❌ JSON decode error: {e}")
                    error_count += 1
                except Exception as e:
                    print(f"  ❌ Error processing: {e}")
                    error_count += 1
            
            # Final count
            final_count = db_manager.get_summaries_count()
            new_summaries = final_count - initial_count
            
            print(f"\n📊 DATABASE TRANSLATION SUMMARY:")
            print(f"  • Files processed: {len(json_files)}")
            print(f"  • Successfully added: {success_count}")
            print(f"  • Skipped (duplicates): {skipped_count}")
            print(f"  • Errors: {error_count}")
            print(f"  • New summaries in database: {new_summaries}")
            print(f"  • Total summaries in database: {final_count}")
            
            if success_count > 0:
                print(f"\n✅ Database translation completed successfully!")
            elif skipped_count > 0:
                print(f"\n⏭️  All summaries already exist in database")
            else:
                print(f"\n⚠️  No summaries were added to the database")
                
        except Exception as e:
            print(f"❌ Database translation phase failed: {e}")
            raise e

    def run_resource_cleanup_phase(self):
        """Run the resource cleanup phase to remove temporary files"""
        print("\n" + "="*60)
        print("PHASE 7: RESOURCE CLEANUP")
        print("="*60)
        

        files = glob.glob("summaries/*.json")
        for file in files:
            os.remove(file)
            print(f"Removed: {file}")

        files = glob.glob("cleaned_text/*.txt")
        for file in files:
            os.remove(file)
            print(f"Removed: {file}")

        files = glob.glob("scraped_html/*.html")
        for file in files:
            os.remove(file)
            print(f"Removed: {file}")
        
    def run_summary_translation_phase(self):
        """Run the summary translation phase to move AI summaries to the database"""
        print("\n" + "="*60)
        print("PHASE 6: SUMMARY TRANSLATION")
        print("="*60)
        
        if not self.summarizer:
            print("AI summarizer not available. Skipping summary translation phase.")
            return
        
        try:
            self.summarizer.translate_summaries_to_db()
            print("Summary translation completed successfully.")
        except Exception as e:
            print(f"Error in summary translation phase: {e}")

    def run_collect_urls_phase(self):
        """Collect URLs from the database"""
        print("\n" + "="*60)
        print("PHASE 1: COLLECTING URLS")
        print("="*60)
        
        try:
            urls = self.collector.collect_from_active_sources()
            return urls
        except Exception as e:
            print(f"Error collecting URLs: {e}")
            return []

    def run_clean_collected_urls_phase(self):
        """Clean collected URLs by removing duplicates and invalid entries"""
        print("\n" + "="*60)
        print("PHASE 2: COLLECTING URLS")
        print("="*60)
        collected_urls = self.db_manager.get_collected_urls()

        for url in collected_urls:
            if url.url[-1] == '/':
                url.url = url.url[:-1]
                deleted_url = self.db_manager.delete_collected_url(url)

    def run_full_pipeline(self, urls=None):
        """Run the complete pipeline"""
        start_time = datetime.now()
        
        print("Starting Investment News Analysis Pipeline")
        print(f"Started at: {start_time}")
        print("="*60)
        
        # Initialize components
        self.initialize_components()
        
        # Phase 1: Collect URLs
        collected_urls = self.run_collect_urls_phase()

        # Phase 2: Clean unwanted urls
        cleaned_url = self.run_clean_collected_urls_phase()

        # Phase 3: Scraping
        scraped_files = self.run_scraping_phase(urls)
        
        # Phase 4: Parsing
        parsed_files = self.run_parsing_phase()
        
        # Phase 5: Summarization
        summary_files = self.run_summarization_phase()

        # Phase 6: Database translation
        database_transformation = self.run_database_transformation_phase()

        # Phase 7: Resource cleanup
        self.run_resource_cleanup_phase()

        
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
            'collected_urls': collected_urls,
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