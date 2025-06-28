#!/usr/bin/env python3
"""
Flask web interface for displaying investment news summaries.
Reads from the summaries JSON files and displays them in a card-based interface.
"""

import os
import json
import glob
import threading
import queue
from datetime import datetime
from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, session
from pathlib import Path

# Import pipeline components
try:
    from web_scraper import NewsScraper
    from html_parser import HTMLParser  
    from ai_summarizer import AISummarizer
    PIPELINE_AVAILABLE = True
except ImportError:
    PIPELINE_AVAILABLE = False

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'  # Change this in production

# Global variables for pipeline status
pipeline_status = {
    'running': False,
    'phase': None,
    'progress': 0,
    'logs': [],
    'last_run': None
}

class PipelineRunner:
    def __init__(self):
        self.status_queue = queue.Queue()
        self.log_queue = queue.Queue()
    
    def update_status(self, phase, progress, message):
        """Update pipeline status"""
        global pipeline_status
        pipeline_status['phase'] = phase
        pipeline_status['progress'] = progress
        pipeline_status['logs'].append({
            'timestamp': datetime.now().isoformat(),
            'message': message
        })
        # Keep only last 100 log entries
        if len(pipeline_status['logs']) > 100:
            pipeline_status['logs'] = pipeline_status['logs'][-100:]
    
    def run_pipeline(self, urls=None, use_selenium=False, model="claude-3-5-sonnet-20241022"):
        """Run the pipeline in a separate thread"""
        global pipeline_status
        
        try:
            pipeline_status['running'] = True
            pipeline_status['logs'] = []
            pipeline_status['last_run'] = datetime.now().isoformat()
            
            self.update_status('initialization', 10, 'Initializing pipeline components...')
            
            # Initialize components
            scraper = NewsScraper(use_selenium=use_selenium)
            parser = HTMLParser()
            
            try:
                summarizer = AISummarizer(model=model)
            except Exception as e:
                self.update_status('error', 0, f'Failed to initialize AI summarizer: {e}')
                return
            
            # Phase 1: Scraping
            self.update_status('scraping', 25, f'Starting web scraping for {len(urls) if urls else "default"} URLs...')
            
            if urls:
                scraped_files = scraper.scrape_urls(urls)
            else:
                default_urls = [
                    "https://www.marketwatch.com/investing",
                    "https://finance.yahoo.com/news",
                    "https://www.cnbc.com/investing/",
                    "https://www.reuters.com/business/finance/",
                    "https://www.bloomberg.com/markets"
                ]
                scraped_files = scraper.scrape_urls(default_urls)
            
            self.update_status('scraping', 40, f'Scraping completed. {len(scraped_files)} files scraped.')
            
            # Phase 2: Parsing
            self.update_status('parsing', 50, 'Starting HTML parsing and text extraction...')
            parsed_files = parser.parse_all_html_files()
            self.update_status('parsing', 65, f'Parsing completed. {len(parsed_files)} files parsed.')
            
            # Phase 3: Summarization
            self.update_status('summarization', 75, 'Starting AI summarization...')
            summary_files = summarizer.batch_process_with_retry()
            self.update_status('summarization', 90, f'Summarization completed. {len(summary_files)} summaries generated.')
            
            # Cleanup
            scraper.close()
            
            self.update_status('completed', 100, f'Pipeline completed successfully! Generated {len(summary_files)} summaries.')
            
        except Exception as e:
            self.update_status('error', 0, f'Pipeline failed: {str(e)}')
        finally:
            pipeline_status['running'] = False

# Initialize pipeline runner
pipeline_runner = PipelineRunner()

class SummaryDataLoader:
    def __init__(self, summaries_dir="summaries"):
        self.summaries_dir = summaries_dir
    
    def load_all_summaries(self):
        """Load all summary JSON files"""
        summaries = []
        
        # Get all JSON files in summaries directory
        json_pattern = os.path.join(self.summaries_dir, "summary_*.json")
        json_files = glob.glob(json_pattern)
        
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    # Extract filename info
                    filename = os.path.basename(json_file)
                    
                    # Add metadata
                    data['filename'] = filename
                    data['file_path'] = json_file
                    
                    # Parse processed_at if available
                    if 'processed_at' in data:
                        try:
                            data['processed_datetime'] = datetime.fromisoformat(data['processed_at'].replace('Z', '+00:00'))
                        except:
                            data['processed_datetime'] = None
                    
                    summaries.append(data)
                    
            except Exception as e:
                print(f"Error loading {json_file}: {e}")
                continue
        
        # Sort by processed time (newest first)
        summaries.sort(key=lambda x: x.get('processed_datetime', datetime.min), reverse=True)
        
        return summaries
    
    def get_summary_stats(self, summaries):
        """Get statistics about the summaries"""
        if not summaries:
            return {}
        
        # Count sentiments
        sentiments = {}
        sectors = set()
        companies = set()
        total_confidence = 0
        confidence_count = 0
        
        for summary in summaries:
            parsed = summary.get('parsed_summary', {})
            
            # Sentiment
            sentiment = parsed.get('sentiment', 'unknown').lower()
            sentiments[sentiment] = sentiments.get(sentiment, 0) + 1
            
            # Sectors
            summary_sectors = parsed.get('sectors_affected', [])
            if isinstance(summary_sectors, list):
                sectors.update(summary_sectors)
            
            # Companies
            summary_companies = parsed.get('companies_mentioned', [])
            if isinstance(summary_companies, list):
                companies.update(summary_companies)
            
            # Confidence
            confidence = parsed.get('confidence_score')
            if confidence is not None:
                try:
                    total_confidence += float(confidence)
                    confidence_count += 1
                except:
                    pass
        
        avg_confidence = total_confidence / confidence_count if confidence_count > 0 else 0
        
        return {
            'total_summaries': len(summaries),
            'sentiments': sentiments,
            'unique_sectors': len(sectors),
            'unique_companies': len(companies),
            'avg_confidence': round(avg_confidence, 2),
            'top_sectors': list(sectors)[:10],
            'top_companies': list(companies)[:10]
        }

# Initialize data loader
data_loader = SummaryDataLoader()

@app.route('/')
def index():
    """Main dashboard page"""
    summaries = data_loader.load_all_summaries()
    stats = data_loader.get_summary_stats(summaries)
    
    return render_template('dashboard.html', 
                         summaries=summaries, 
                         stats=stats)

@app.route('/api/summaries')
def api_summaries():
    """API endpoint to get all summaries as JSON"""
    summaries = data_loader.load_all_summaries()
    return jsonify(summaries)

@app.route('/api/stats')
def api_stats():
    """API endpoint to get summary statistics"""
    summaries = data_loader.load_all_summaries()
    stats = data_loader.get_summary_stats(summaries)
    return jsonify(stats)

@app.route('/admin')
def admin():
    """Admin dashboard page"""
    return render_template('admin.html', 
                         pipeline_status=pipeline_status,
                         pipeline_available=PIPELINE_AVAILABLE)

@app.route('/admin/run_pipeline', methods=['POST'])
def run_pipeline():
    """Start the pipeline"""
    if not PIPELINE_AVAILABLE:
        flash('Pipeline components not available. Make sure all modules are installed.', 'error')
        return redirect(url_for('admin'))
    
    if pipeline_status['running']:
        flash('Pipeline is already running!', 'warning')
        return redirect(url_for('admin'))
    
    # Get form data
    urls_text = request.form.get('urls', '').strip()
    use_selenium = 'use_selenium' in request.form
    model = request.form.get('model', 'claude-3-5-sonnet-20241022')
    
    # Parse URLs
    urls = []
    if urls_text:
        urls = [url.strip() for url in urls_text.split('\n') if url.strip()]
    
    # Start pipeline in background thread
    thread = threading.Thread(
        target=pipeline_runner.run_pipeline,
        args=(urls, use_selenium, model)
    )
    thread.daemon = True
    thread.start()
    
    flash('Pipeline started successfully!', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/status')
def admin_status():
    """Get current pipeline status (for AJAX updates)"""
    return jsonify(pipeline_status)

@app.route('/admin/stop_pipeline', methods=['POST'])
def stop_pipeline():
    """Stop the pipeline (note: this is a soft stop)"""
    global pipeline_status
    if pipeline_status['running']:
        pipeline_status['running'] = False
        pipeline_status['phase'] = 'stopped'
        flash('Pipeline stop requested. It may take a moment to fully stop.', 'info')
    else:
        flash('No pipeline is currently running.', 'info')
    
    return redirect(url_for('admin'))

@app.route('/admin/clear_logs', methods=['POST'])
def clear_logs():
    """Clear pipeline logs"""
    global pipeline_status
    pipeline_status['logs'] = []
    flash('Logs cleared successfully.', 'success')
    return redirect(url_for('admin'))
    """View individual summary details"""
    summaries = data_loader.load_all_summaries()
    
    # Find the specific summary
    summary = None
    for s in summaries:
        if s['filename'] == filename:
            summary = s
            break
    
    if not summary:
        return "Summary not found", 404
    
    return render_template('summary_detail.html', summary=summary)

@app.template_filter('basename')
def basename_filter(path):
    """Get basename of a file path"""
    if not path:
        return 'Unknown'
    return os.path.basename(path)

@app.template_filter('timeago')
def timeago_filter(dt):
    """Template filter to show time ago"""
    if not dt:
        return "Unknown"
    
    now = datetime.now()
    if dt.tzinfo:
        # Make now timezone aware
        from datetime import timezone
        now = now.replace(tzinfo=timezone.utc)
    
    diff = now - dt
    
    if diff.days > 0:
        return f"{diff.days} day{'s' if diff.days != 1 else ''} ago"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    else:
        return "Just now"

@app.template_filter('sentiment_color')
def sentiment_color_filter(sentiment):
    """Get color class for sentiment"""
    if not sentiment:
        return 'secondary'
    
    sentiment = sentiment.lower()
    if sentiment == 'positive':
        return 'success'
    elif sentiment == 'negative':
        return 'danger'
    else:
        return 'warning'

@app.template_filter('confidence_color')
def confidence_color_filter(confidence):
    """Get color class for confidence score"""
    try:
        score = float(confidence)
        if score >= 0.8:
            return 'success'
        elif score >= 0.6:
            return 'warning'
        else:
            return 'danger'
    except:
        return 'secondary'

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static/css', exist_ok=True)
    os.makedirs('static/js', exist_ok=True)
    
    print("Starting Investment News Dashboard...")
    print("Visit http://localhost:5000 to view the dashboard")
    
    app.run(debug=True, host='0.0.0.0', port=5000)