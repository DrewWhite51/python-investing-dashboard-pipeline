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
import uuid
from datetime import datetime
from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, session
from pathlib import Path

# Import pipeline components
try:
    from web_scraper import NewsScraper
    from html_parser import HTMLParser  
    from ai_summarizer import AISummarizer
    from collect_urls import URLCollector
    from database import DatabaseManager
    PIPELINE_AVAILABLE = True
except ImportError:
    PIPELINE_AVAILABLE = False

app = Flask(__name__)
DB_PATH = "news_pipeline.db"  # Define this once
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
                    
                    # Skip if parsed_summary is missing
                    if 'parsed_summary' not in data:
                        continue
                    
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
                pass  # Silently skip broken JSON files
        
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
db_manager = DatabaseManager()
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
    sources = db_manager.get_news_sources()
    categories = db_manager.get_categories()
    
    # Convert to dict format for template compatibility
    sources_dict = []
    for source in sources:
        sources_dict.append({
            'id': source.id,
            'name': source.name,
            'url': source.url,
            'category': source.category,
            'description': source.description,
            'active': source.active,
            'added_at': source.added_at,
            'last_collected': source.last_collected,
            'collection_count': source.collection_count,
            'avg_articles_found': source.avg_articles_found
        })
    
    return render_template('sources.html', 
                         sources=sources_dict, 
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
    
    if db_manager.add_news_source(name, url, category, description, active):
        flash(f'News source "{name}" added successfully.', 'success')
    else:
        flash('Failed to add news source. Name or URL might already exist.', 'error')
    
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
    
    if db_manager.update_news_source(source_id, 
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
    source = db_manager.get_news_source_by_id(source_id)
    if source:
        if db_manager.delete_news_source(source_id):
            flash(f'News source "{source.name}" deleted successfully.', 'success')
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
    
    # Get active sources from database
    active_sources = db_manager.get_news_sources(active_only=True)
    
    if not active_sources:
        flash('No active news sources found. Please add and activate some sources first.', 'warning')
        return redirect(url_for('manage_sources'))
    
    try:
        # Initialize URL collector
        collector = URLCollector(use_selenium=use_selenium)
        
        # Collect URLs (this now saves directly to database)
        results = collector.collect_urls_from_sources(active_sources)
        
        # Store batch info in session for viewing
        if results['success']:
            session['latest_batch_id'] = results['batch_id']
            session['collection_timestamp'] = datetime.now().isoformat()
            flash(f'URL collection completed! Found {results["total_urls"]} article URLs from {results["sources_processed"]} sources.', 'success')
        else:
            flash(f'URL collection failed: {results["error_message"]}', 'error')
        
        collector.close()
        
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

# ===== DATABASE ADMIN ROUTES =====

@app.route('/admin/database')
def database_admin():
    """Database administration page"""
    try:
        # Get database schema
        schema = db_manager.get_database_schema()
        
        # Get database statistics
        db_stats = db_manager.get_database_stats()
        
        return render_template('database_admin.html', 
                             schema=schema,
                             db_stats=db_stats)
    except Exception as e:
        flash(f'Error loading database admin: {e}', 'error')
        return redirect(url_for('admin'))

@app.route('/admin/database/query', methods=['POST'])
def execute_database_query():
    """Execute any database query (admin only)"""
    query = request.form.get('query', '').strip()
    
    if not query:
        return jsonify({'success': False, 'error': 'No query provided'})
    
    try:
        results, columns, operation = db_manager.execute_any_query(query)
        return jsonify({
            'success': True,
            'results': results,
            'columns': columns,
            'operation': operation,
            'row_count': len(results)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/database/table/<table_name>')
def get_table_data(table_name):
    """Get data from a specific table"""
    try:
        results, columns = db_manager.get_table_data(table_name)
        return jsonify({
            'success': True,
            'results': results,
            'columns': columns,
            'table_name': table_name
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/debug_db')
def debug_database():
    """Debug database information"""
    db_manager.debug_database_info()
    return jsonify({
        'db_path': db_manager.db_path,
        'absolute_path': os.path.abspath(db_manager.db_path),
        'exists': os.path.exists(db_manager.db_path)
    })

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
    # Ensure database is initialized
    print(f"Using database: {os.path.abspath(DB_PATH)}")
    
    # Initialize database if needed
    try:
        db_manager.init_database()
        print("Database initialized successfully")
        
        # Debug: Check tables
        db_manager.debug_database_info()
        
    except Exception as e:
        print(f"Database initialization error: {e}")
    
    # Create necessary directories
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static/css', exist_ok=True)
    os.makedirs('static/js', exist_ok=True)
    
    print("Starting Investment News Dashboard...")
    print("Visit http://localhost:5000 to view the dashboard")
    
    app.run(debug=True, host='0.0.0.0', port=5000)