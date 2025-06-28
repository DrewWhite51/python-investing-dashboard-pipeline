#!/usr/bin/env python3
"""
Flask web interface for displaying investment news summaries.
Reads from the summaries JSON files and displays them in a card-based interface.
"""

import os
import json
import glob
from datetime import datetime
from flask import Flask, render_template, jsonify, request
from pathlib import Path

app = Flask(__name__)

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