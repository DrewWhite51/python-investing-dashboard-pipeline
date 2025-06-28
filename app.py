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
    from collect_urls import URLCollector
    from news_sources import NewsSourcesManager
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

# Initialize components
pipeline_runner = PipelineRunner()
news_sources_manager = NewsSourcesManager()
data_loader = SummaryDataLoader()

# ===== MAIN ROUTES =====

@app.route('/')
def index():
    """Main dashboard page"""
    summaries = data_loader.load_all_summaries()
    stats = data_loader.get_summary_stats(summaries)
    
    return render_template('dashboard.html', 
                         summaries=summaries, 
                         stats=stats)

@app.route('/summary/<filename>')
def view_summary(filename):
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

# ===== API ROUTES =====

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

# ===== ADMIN ROUTES =====

@app.route('/admin')
def admin():
    """Admin dashboard page"""
    return render_template('admin.html', 
                         pipeline_status=pipeline_status,
                         pipeline_available=PIPELINE_AVAILABLE)

@app.route('/admin/status')
def admin_status():
    """Get current pipeline status (for AJAX updates)"""
    return jsonify(pipeline_status)

# ===== PIPELINE CONTROL ROUTES =====

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

@app.route('/admin/run_pipeline_with_collected', methods=['POST'])
def run_pipeline_with_collected():
    """Run pipeline with collected URLs"""
    if not PIPELINE_AVAILABLE:
        flash('Pipeline components not available.', 'error')
        return redirect(url_for('admin'))
    
    if pipeline_status['running']:
        flash('Pipeline is already running!', 'warning')
        return redirect(url_for('admin'))
    
    collected_urls = session.get('collected_urls', [])
    if not collected_urls:
        flash('No collected URLs found. Please collect URLs first.', 'warning')
        return redirect(url_for('admin'))
    
    # Get form data
    use_selenium = 'use_selenium' in request.form
    model = request.form.get('model', 'claude-3-5-sonnet-20241022')
    
    # Start pipeline with collected URLs
    thread = threading.Thread(
        target=pipeline_runner.run_pipeline,
        args=(collected_urls, use_selenium, model)
    )
    thread.daemon = True
    thread.start()
    
    flash(f'Pipeline started with {len(collected_urls)} collected URLs!', 'success')
    return redirect(url_for('admin'))

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

# ===== NEWS SOURCES MANAGEMENT ROUTES =====

@app.route('/admin/sources')
def manage_sources():
    """News sources management page"""
    sources = news_sources_manager.get_all_sources()
    categories = news_sources_manager.get_categories()
    return render_template('sources.html', 
                         sources=sources, 
                         categories=categories)

@app.route('/admin/sources/add', methods=['POST'])
def add_source():
    """Add a new news source"""
    name = request.form.get('name', '').strip()
    url = request.form.get('url', '').strip()
    category = request.form.get('category', '').strip()
    new_category = request.form.get('new_category', '').strip()
    description = request.form.get('description', '').strip()
    active = 'active' in request.form
    
    # Use new category if provided
    if new_category:
        category = new_category
    
    if not name or not url:
        flash('Name and URL are required.', 'error')
        return redirect(url_for('manage_sources'))
    
    if news_sources_manager.add_source(name, url, category, description, active):
        flash(f'News source "{name}" added successfully.', 'success')
    else:
        flash('Failed to add news source.', 'error')
    
    return redirect(url_for('manage_sources'))

@app.route('/admin/sources/update/<int:source_id>', methods=['POST'])
def update_source(source_id):
    """Update an existing news source"""
    name = request.form.get('name', '').strip()
    url = request.form.get('url', '').strip()
    category = request.form.get('category', '').strip()
    description = request.form.get('description', '').strip()
    active = 'active' in request.form
    
    if not name or not url:
        flash('Name and URL are required.', 'error')
        return redirect(url_for('manage_sources'))
    
    if news_sources_manager.update_source(source_id, 
                                        name=name, 
                                        url=url, 
                                        category=category, 
                                        description=description, 
                                        active=active):
        flash(f'News source updated successfully.', 'success')
    else:
        flash('Failed to update news source.', 'error')
    
    return redirect(url_for('manage_sources'))

@app.route('/admin/sources/delete/<int:source_id>', methods=['POST'])
def delete_source(source_id):
    """Delete a news source"""
    source = news_sources_manager.get_source_by_id(source_id)
    if source:
        if news_sources_manager.delete_source(source_id):
            flash(f'News source "{source["name"]}" deleted successfully.', 'success')
        else:
            flash('Failed to delete news source.', 'error')
    else:
        flash('News source not found.', 'error')
    
    return redirect(url_for('manage_sources'))

# ===== URL COLLECTION ROUTES =====

@app.route('/admin/collect_urls', methods=['POST'])
def collect_urls():
    """Collect URLs from news sources"""
    if not PIPELINE_AVAILABLE:
        flash('URL collection components not available.', 'error')
        return redirect(url_for('admin'))
    
    use_selenium = 'use_selenium' in request.form
    
    # Get active source URLs
    active_urls = news_sources_manager.get_active_urls()
    
    if not active_urls:
        flash('No active news sources found. Please add and activate some sources first.', 'warning')
        return redirect(url_for('manage_sources'))
    
    try:
        # Initialize URL collector
        collector = URLCollector(use_selenium=use_selenium)
        
        # Collect URLs
        collection_results = collector.collect_urls_from_multiple_pages(active_urls)
        
        # Update collection statistics
        for base_url, result in collection_results['results'].items():
            if result['success']:
                news_sources_manager.update_collection_stats(base_url, result['count'])
        
        # Get flat list of URLs for session storage
        article_urls = collector.get_flat_url_list()
        session['collected_urls'] = article_urls
        session['collection_timestamp'] = datetime.now().isoformat()
        
        collector.close()
        
        flash(f'URL collection completed! Found {len(article_urls)} article URLs from {len(active_urls)} sources.', 'success')
        
    except Exception as e:
        flash(f'URL collection failed: {str(e)}', 'error')
    
    return redirect(url_for('admin'))

@app.route('/admin/collected_urls')
def view_collected_urls():
    """View collected URLs"""
    collected_urls = session.get('collected_urls', [])
    collection_timestamp = session.get('collection_timestamp')
    
    return render_template('collected_urls.html', 
                         urls=collected_urls,
                         collection_timestamp=collection_timestamp,
                         total_count=len(collected_urls))

# ===== TEMPLATE FILTERS =====

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

# ===== MAIN EXECUTION =====

if __name__ == '__main__':
    # Create necessary directories
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static/css', exist_ok=True)
    os.makedirs('static/js', exist_ok=True)
    
    print("Starting Investment News Dashboard...")
    print("Visit http://localhost:5000 to view the dashboard")
    
    app.run(debug=True, host='0.0.0.0', port=5000)