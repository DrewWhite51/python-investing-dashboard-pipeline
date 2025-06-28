#!/usr/bin/env python3
"""
AI summarizer for cleaned news articles.
Sends articles to Anthropic Claude API for investment-focused summarization.
"""

import os
import glob
import json
from datetime import datetime
from pathlib import Path
import anthropic
import time

class AISummarizer:
    def __init__(self, api_key=None, input_dir="cleaned_text", output_dir="summaries", model="claude-3-5-sonnet-20241022"):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.model = model
        
        # Initialize Anthropic client
        self.client = anthropic.Anthropic(
            api_key=api_key or os.getenv('ANTHROPIC_API_KEY')
        )
        
        if not self.client.api_key:
            raise ValueError("Anthropic API key not provided. Set ANTHROPIC_API_KEY environment variable or pass api_key parameter.")
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Investment-focused system prompt
        self.system_prompt = """You are an expert financial analyst specializing in investment news summarization. 
        Your task is to analyze news articles and extract key investment insights.

        For each article, provide a JSON response with the following structure:
        {
            "summary": "A concise 2-3 sentence summary of the main points",
            "investment_implications": "Key implications for investors",
            "key_metrics": ["list", "of", "important", "financial", "metrics", "mentioned"],
            "companies_mentioned": ["list", "of", "companies", "or", "tickers"],
            "sectors_affected": ["list", "of", "market", "sectors"],
            "sentiment": "positive/negative/neutral",
            "risk_factors": ["potential", "risks", "mentioned"],
            "opportunities": ["investment", "opportunities", "identified"],
            "time_horizon": "short-term/medium-term/long-term impact",
            "confidence_score": 0.85
        }

        Focus on:
        - Market impact and investment implications
        - Financial metrics, earnings, revenue, growth rates
        - Company performance and outlook
        - Economic indicators and trends
        - Risk factors and opportunities
        - Regulatory changes affecting investments
        
        Be objective and factual. If the article doesn't contain investment-relevant information, indicate this in your response."""
    
    def read_text_file(self, filepath):
        """Read and return content of text file"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"Error reading {filepath}: {e}")
            return None
    
    def truncate_text(self, text, max_tokens=150000):
        """Truncate text to fit within Claude's context limits"""
        # Claude 3.5 Sonnet has ~200k token context window
        # Rough estimation: 1 token ≈ 4 characters
        max_chars = max_tokens * 4
        
        if len(text) <= max_chars:
            return text
        
        # Try to truncate at a sentence boundary
        truncated = text[:max_chars]
        last_period = truncated.rfind('.')
        
        if last_period > max_chars * 0.8:  # If we can find a period in the last 20%
            return truncated[:last_period + 1]
        else:
            return truncated + "..."
    
    def summarize_article(self, text_content):
        """Send article to Anthropic Claude for summarization"""
        try:
            # Truncate if necessary
            truncated_content = self.truncate_text(text_content, max_tokens=150000)
            
            # Create message with Claude
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                temperature=0.3,  # Lower temperature for more consistent outputs
                system=self.system_prompt,
                messages=[
                    {
                        "role": "user", 
                        "content": f"Please analyze this financial news article:\n\n{truncated_content}"
                    }
                ]
            )
            
            return response.content[0].text
            
        except Exception as e:
            print(f"Error calling Anthropic API: {e}")
            return None
    
    def process_text_file(self, text_filepath):
        """Process a single text file and generate summary"""
        print(f"Summarizing: {text_filepath}")
        
        # Read text content
        text_content = self.read_text_file(text_filepath)
        if not text_content:
            return None
        
        # Get AI summary
        summary = self.summarize_article(text_content)
        if not summary:
            return None
        
        # Generate output filename
        input_filename = Path(text_filepath).stem
        output_filename = f"summary_{input_filename}.json"
        output_filepath = os.path.join(self.output_dir, output_filename)
        
        # Prepare output data
        output_data = {
            "source_file": text_filepath,
            "processed_at": datetime.now().isoformat(),
            "model_used": self.model,
            "raw_response": summary
        }
        
        # Try to parse AI response as JSON
        try:
            parsed_summary = json.loads(summary)
            output_data["parsed_summary"] = parsed_summary
        except json.JSONDecodeError:
            # If not valid JSON, store as raw text
            output_data["summary_text"] = summary
        
        # Save summary to file
        try:
            with open(output_filepath, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            
            print(f"Saved summary: {output_filepath}")
            return output_filepath
            
        except Exception as e:
            print(f"Error saving summary: {e}")
            return None
    
    def process_all_text_files(self, delay_between_requests=1):
        """Process all text files in the input directory"""
        # Find all text files
        text_pattern = os.path.join(self.input_dir, "clean_*.txt")
        text_files = glob.glob(text_pattern)
        
        if not text_files:
            print(f"No clean text files found in {self.input_dir}")
            return []
        
        print(f"Found {len(text_files)} text files to summarize")
        
        summary_files = []
        for i, text_file in enumerate(text_files, 1):
            print(f"Processing {i}/{len(text_files)}")
            
            summary_file = self.process_text_file(text_file)
            if summary_file:
                summary_files.append(summary_file)
            
            # Rate limiting - be respectful to API
            if i < len(text_files):  # Don't sleep after the last request
                time.sleep(delay_between_requests)
        
        return summary_files
    
    def batch_process_with_retry(self, max_retries=3, delay_between_requests=2):
        """Process all files with retry logic for failed requests"""
        summary_files = []
        failed_files = []
        
        text_pattern = os.path.join(self.input_dir, "clean_*.txt")
        text_files = glob.glob(text_pattern)
        
        for text_file in text_files:
            retry_count = 0
            success = False
            
            while retry_count < max_retries and not success:
                try:
                    summary_file = self.process_text_file(text_file)
                    if summary_file:
                        summary_files.append(summary_file)
                        success = True
                    else:
                        retry_count += 1
                        
                except Exception as e:
                    print(f"Attempt {retry_count + 1} failed for {text_file}: {e}")
                    retry_count += 1
                    time.sleep(delay_between_requests * 2)  # Longer delay on failure
            
            if not success:
                failed_files.append(text_file)
                print(f"Failed to process {text_file} after {max_retries} attempts")
            
            # Rate limiting
            time.sleep(delay_between_requests)
        
        if failed_files:
            print(f"\nFailed to process {len(failed_files)} files:")
            for file in failed_files:
                print(f"  - {file}")
        
        return summary_files


def main():
    """Example usage"""
    # Make sure to set your Anthropic API key as an environment variable
    # export ANTHROPIC_API_KEY="your-api-key-here"
    
    try:
        summarizer = AISummarizer(model="claude-3-5-sonnet-20241022")  # or "claude-3-opus-20240229" for best results
        
        # Process all text files
        summary_files = summarizer.batch_process_with_retry()
        
        print(f"\nSuccessfully processed {len(summary_files)} files:")
        for file in summary_files:
            print(f"  - {file}")
            
    except ValueError as e:
        print(f"Configuration error: {e}")
        print("Please set your Anthropic API key:")
        print("  export ANTHROPIC_API_KEY='your-api-key-here'")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()