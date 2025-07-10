#!/usr/bin/env python3
"""
AI summarizer for cleaned news articles using Ollama (free local LLM).
Sends articles to local Ollama instance for investment-focused summarization.
"""

import os
import glob
import json
import requests
from datetime import datetime
from pathlib import Path
import time

class OllamaAISummarizer:
    def __init__(self, input_dir="cleaned_text", output_dir="summaries", 
                 model="llama3.1:8b", ollama_url="http://localhost:11434"):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.model = model
        self.ollama_url = ollama_url
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Test Ollama connection
        self._test_connection()
        
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
    "time_horizon": "short-term/medium-term/long-term",
    "confidence_score": 0.85
}

Focus on:
- Market impact and investment implications
- Financial metrics, earnings, revenue, growth rates
- Company performance and outlook
- Economic indicators and trends
- Risk factors and opportunities
- Regulatory changes affecting investments

Be objective and factual. Only return the JSON object, no additional text."""

    def _test_connection(self):
        """Test connection to Ollama"""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                model_names = [m['name'] for m in models]
                print(f"✅ Connected to Ollama. Available models: {model_names}")
                
                if self.model not in model_names:
                    print(f"⚠️  Model '{self.model}' not found. Available: {model_names}")
                    print(f"Run: ollama pull {self.model}")
                    raise ValueError(f"Model {self.model} not available")
            else:
                raise ConnectionError("Failed to connect to Ollama")
        except requests.RequestException as e:
            print(f"❌ Cannot connect to Ollama at {self.ollama_url}")
            print("Make sure Ollama is running: ollama serve")
            raise ConnectionError(f"Ollama connection failed: {e}")

    def read_text_file(self, filepath):
        """Read and return content of text file"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"Error reading {filepath}: {e}")
            return None

    def truncate_text(self, text, max_chars=8000):
        """Truncate text for local models (they typically have smaller context windows)"""
        if len(text) <= max_chars:
            return text
        
        # Try to truncate at a sentence boundary
        truncated = text[:max_chars]
        last_period = truncated.rfind('.')
        
        if last_period > max_chars * 0.8:
            return truncated[:last_period + 1]
        else:
            return truncated + "..."

    def summarize_article(self, text_content):
        """Send article to Ollama for summarization"""
        try:
            # Truncate if necessary
            truncated_content = self.truncate_text(text_content)
            
            # Prepare the prompt
            full_prompt = f"{self.system_prompt}\n\nPlease analyze this financial news article:\n\n{truncated_content}\n\nProvide only the JSON response:"
            
            # Call Ollama API
            payload = {
                "model": self.model,
                "prompt": full_prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "top_p": 0.9,
                    "num_predict": 1000
                }
            }
            
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
                timeout=120  # Local processing can take time
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('response', '').strip()
            else:
                print(f"Ollama API error: {response.status_code} - {response.text}")
                return None
                
        except requests.RequestException as e:
            print(f"Error calling Ollama API: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error: {e}")
            return None

    def clean_json_response(self, response_text):
        """Clean and extract JSON from model response"""
        if not response_text:
            return None
            
        # Remove markdown code blocks if present
        if "```json" in response_text:
            start = response_text.find("```json") + 7
            end = response_text.find("```", start)
            if end != -1:
                response_text = response_text[start:end].strip()
        elif "```" in response_text:
            start = response_text.find("```") + 3
            end = response_text.find("```", start)
            if end != -1:
                response_text = response_text[start:end].strip()
        
        # Try to find JSON object boundaries
        start_brace = response_text.find('{')
        end_brace = response_text.rfind('}')
        
        if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
            response_text = response_text[start_brace:end_brace + 1]
        
        return response_text.strip()

    def process_text_file(self, text_filepath):
        """Process a single text file and generate summary"""
        print(f"📄 Summarizing: {os.path.basename(text_filepath)}")
        
        # Read text content
        text_content = self.read_text_file(text_filepath)
        if not text_content:
            return None
        
        # Get AI summary
        summary = self.summarize_article(text_content)
        if not summary:
            return None
        
        # Clean the response
        cleaned_summary = self.clean_json_response(summary)
        
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
            parsed_summary = json.loads(cleaned_summary)
            output_data["parsed_summary"] = parsed_summary
            print(f"  ✅ Successfully parsed JSON response")
        except json.JSONDecodeError as e:
            print(f"  ⚠️  Failed to parse JSON: {e}")
            print(f"  Raw response: {cleaned_summary[:200]}...")
            output_data["summary_text"] = cleaned_summary
            output_data["parse_error"] = str(e)
        
        # Save summary to file
        try:
            with open(output_filepath, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            
            print(f"  💾 Saved: {output_filename}")
            return output_filepath
            
        except Exception as e:
            print(f"  ❌ Error saving: {e}")
            return None

    def batch_process_with_retry(self, max_retries=3, delay_between_requests=2):
        """Process all files with retry logic"""
        summary_files = []
        failed_files = []
        
        text_pattern = os.path.join(self.input_dir, "clean_*.txt")
        text_files = glob.glob(text_pattern)
        
        if not text_files:
            print(f"No files found matching: {text_pattern}")
            return summary_files
        
        print(f"🚀 Processing {len(text_files)} files with Ollama...")
        print(f"📊 Model: {self.model}")
        print(f"🔗 Ollama URL: {self.ollama_url}")
        
        for i, text_file in enumerate(text_files, 1):
            print(f"\n[{i}/{len(text_files)}] Processing: {os.path.basename(text_file)}")
            
            retry_count = 0
            success = False
            
            while retry_count < max_retries and not success:
                try:
                    summary_file = self.process_text_file(text_file)
                    if summary_file:
                        summary_files.append(summary_file)
                        success = True
                        print(f"  ✅ Success!")
                        
                        # Optional: Remove processed file
                        # os.remove(text_file)
                    else:
                        retry_count += 1
                        print(f"  ⚠️  Attempt {retry_count} failed, retrying...")
                        
                except Exception as e:
                    print(f"  ❌ Attempt {retry_count + 1} failed: {e}")
                    retry_count += 1
                    time.sleep(delay_between_requests * 2)
            
            if not success:
                failed_files.append(text_file)
                print(f"  ❌ Failed after {max_retries} attempts")
            
            # Small delay between requests (less needed for local processing)
            if i < len(text_files):
                time.sleep(delay_between_requests)
        
        print(f"\n📊 Processing Complete!")
        print(f"✅ Successful: {len(summary_files)}")
        print(f"❌ Failed: {len(failed_files)}")
        
        if failed_files:
            print(f"\nFailed files:")
            for file in failed_files:
                print(f"  - {os.path.basename(file)}")
        
        return summary_files

    def process_all_text_files(self, delay_between_requests=1):
        """Simple processing of all text files"""
        return self.batch_process_with_retry(delay_between_requests=delay_between_requests)


def main():
    """Example usage"""
    try:
        # You can try different models:
        # "llama3.1:8b" - Good balance of speed and quality
        # "llama3.1:70b" - Better quality but slower (needs more RAM)
        # "qwen2.5:14b" - Good for analysis tasks
        # "mistral:7b" - Fast and efficient
        
        summarizer = OllamaAISummarizer(
            model="llama3.1:8b",  # Change this to your preferred model
            ollama_url="http://localhost:11434"
        )
        
        # Process all text files
        summary_files = summarizer.batch_process_with_retry(
            max_retries=3,
            delay_between_requests=1  # Can be lower since it's local
        )
        
        print(f"\n🎉 Successfully processed {len(summary_files)} files!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure Ollama is installed: https://ollama.ai")
        print("2. Start Ollama: ollama serve")
        print("3. Pull a model: ollama pull llama3.1:8b")


if __name__ == "__main__":
    main()