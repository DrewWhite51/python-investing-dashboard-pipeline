#!/usr/bin/env python3
"""
News sources manager for storing and managing base URLs for URL collection.
"""

import json
import os
from datetime import datetime
from typing import List, Dict

class NewsSourcesManager:
    def __init__(self, sources_file="news_sources.json"):
        self.sources_file = sources_file
        self.sources = self.load_sources()
    
    def load_sources(self):
        """Load news sources from file"""
        if os.path.exists(self.sources_file):
            try:
                with open(self.sources_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading sources: {e}")
                return self.get_default_sources()
        else:
            # Create default sources file
            default_sources = self.get_default_sources()
            self.save_sources(default_sources)
            return default_sources
    
    def get_default_sources(self):
        """Get default news sources"""
        return {
            "sources": [
                {
                    "id": 1,
                    "name": "CoinDesk",
                    "url": "https://www.coindesk.com/",
                    "category": "Cryptocurrency",
                    "active": True,
                    "description": "Leading cryptocurrency and blockchain news",
                    "added_at": datetime.now().isoformat(),
                    "last_collected": None,
                    "collection_count": 0,
                    "avg_articles_found": 0
                },
                {
                    "id": 2,
                    "name": "MarketWatch Investing",
                    "url": "https://www.marketwatch.com/investing",
                    "category": "Stock Market",
                    "active": True,
                    "description": "MarketWatch investing section",
                    "added_at": datetime.now().isoformat(),
                    "last_collected": None,
                    "collection_count": 0,
                    "avg_articles_found": 0
                },
                {
                    "id": 3,
                    "name": "Yahoo Finance News",
                    "url": "https://finance.yahoo.com/news",
                    "category": "General Finance",
                    "active": True,
                    "description": "Yahoo Finance news section",
                    "added_at": datetime.now().isoformat(),
                    "last_collected": None,
                    "collection_count": 0,
                    "avg_articles_found": 0
                },
                {
                    "id": 4,
                    "name": "CNBC Investing",
                    "url": "https://www.cnbc.com/investing/",
                    "category": "Business News",
                    "active": True,
                    "description": "CNBC investing section",
                    "added_at": datetime.now().isoformat(),
                    "last_collected": None,
                    "collection_count": 0,
                    "avg_articles_found": 0
                },
                {
                    "id": 5,
                    "name": "Reuters Business & Finance",
                    "url": "https://www.reuters.com/business/finance/",
                    "category": "Business News",
                    "active": True,
                    "description": "Reuters business and finance section",
                    "added_at": datetime.now().isoformat(),
                    "last_collected": None,
                    "collection_count": 0,
                    "avg_articles_found": 0
                },
                {
                    "id": 6,
                    "name": "Bloomberg Markets",
                    "url": "https://www.bloomberg.com/markets",
                    "category": "Markets",
                    "active": True,
                    "description": "Bloomberg markets section",
                    "added_at": datetime.now().isoformat(),
                    "last_collected": None,
                    "collection_count": 0,
                    "avg_articles_found": 0
                },
                {
                    "id": 7,
                    "name": "Seeking Alpha",
                    "url": "https://seekingalpha.com/",
                    "category": "Investment Analysis",
                    "active": False,
                    "description": "Investment research and analysis",
                    "added_at": datetime.now().isoformat(),
                    "last_collected": None,
                    "collection_count": 0,
                    "avg_articles_found": 0
                },
                {
                    "id": 8,
                    "name": "The Motley Fool",
                    "url": "https://www.fool.com/investing/",
                    "category": "Investment Advice",
                    "active": False,
                    "description": "Investment advice and stock analysis",
                    "added_at": datetime.now().isoformat(),
                    "last_collected": None,
                    "collection_count": 0,
                    "avg_articles_found": 0
                }
            ],
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "version": "1.0"
            }
        }
    
    def save_sources(self, sources=None):
        """Save sources to file"""
        if sources is None:
            sources = self.sources
        
        sources["metadata"]["last_updated"] = datetime.now().isoformat()
        
        try:
            with open(self.sources_file, 'w', encoding='utf-8') as f:
                json.dump(sources, f, indent=2, ensure_ascii=False)
            self.sources = sources
            return True
        except Exception as e:
            print(f"Error saving sources: {e}")
            return False
    
    def get_all_sources(self):
        """Get all news sources"""
        return self.sources["sources"]
    
    def get_active_sources(self):
        """Get only active news sources"""
        return [source for source in self.sources["sources"] if source["active"]]
    
    def get_active_urls(self):
        """Get URLs of active sources"""
        return [source["url"] for source in self.get_active_sources()]
    
    def add_source(self, name, url, category="General", description="", active=True):
        """Add a new news source"""
        # Get next ID
        existing_ids = [source["id"] for source in self.sources["sources"]]
        next_id = max(existing_ids) + 1 if existing_ids else 1
        
        new_source = {
            "id": next_id,
            "name": name,
            "url": url,
            "category": category,
            "active": active,
            "description": description,
            "added_at": datetime.now().isoformat(),
            "last_collected": None,
            "collection_count": 0,
            "avg_articles_found": 0
        }
        
        self.sources["sources"].append(new_source)
        return self.save_sources()
    
    def update_source(self, source_id, **kwargs):
        """Update an existing source"""
        for source in self.sources["sources"]:
            if source["id"] == source_id:
                for key, value in kwargs.items():
                    if key in source:
                        source[key] = value
                return self.save_sources()
        return False
    
    def delete_source(self, source_id):
        """Delete a source"""
        self.sources["sources"] = [
            source for source in self.sources["sources"] 
            if source["id"] != source_id
        ]
        return self.save_sources()
    
    def update_collection_stats(self, url, articles_found):
        """Update collection statistics for a source"""
        for source in self.sources["sources"]:
            if source["url"] == url:
                source["last_collected"] = datetime.now().isoformat()
                source["collection_count"] += 1
                
                # Update average articles found
                if source["collection_count"] == 1:
                    source["avg_articles_found"] = articles_found
                else:
                    current_avg = source["avg_articles_found"]
                    source["avg_articles_found"] = round(
                        (current_avg * (source["collection_count"] - 1) + articles_found) / source["collection_count"],
                        1
                    )
                
                self.save_sources()
                break
    
    def get_source_by_id(self, source_id):
        """Get a source by ID"""
        for source in self.sources["sources"]:
            if source["id"] == source_id:
                return source
        return None
    
    def get_sources_by_category(self, category):
        """Get sources by category"""
        return [source for source in self.sources["sources"] if source["category"] == category]
    
    def get_categories(self):
        """Get all unique categories"""
        categories = set()
        for source in self.sources["sources"]:
            categories.add(source["category"])
        return sorted(list(categories))


def main():
    """Example usage"""
    manager = NewsSourcesManager()
    
    print("All sources:")
    for source in manager.get_all_sources():
        status = "✓" if source["active"] else "✗"
        print(f"{status} {source['name']} - {source['url']}")
    
    print(f"\nActive URLs:")
    for url in manager.get_active_urls():
        print(f"  {url}")
    
    print(f"\nCategories: {manager.get_categories()}")


if __name__ == "__main__":
    main()