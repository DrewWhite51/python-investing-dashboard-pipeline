#!/usr/bin/env python3
"""
Setup script for initializing the database with default news sources.
"""

from database import DatabaseManager

def setup_default_sources():
    """Add default news sources to the database"""
    db = DatabaseManager()
    
    default_sources = [
        {
            'name': 'CoinDesk',
            'url': 'https://www.coindesk.com/',
            'category': 'Cryptocurrency',
            'description': 'Leading cryptocurrency and blockchain news',
            'active': True
        },
        {
            'name': 'MarketWatch Investing',
            'url': 'https://www.marketwatch.com/investing',
            'category': 'Stock Market',
            'description': 'MarketWatch investing section',
            'active': True
        },
        {
            'name': 'Yahoo Finance News',
            'url': 'https://finance.yahoo.com/news',
            'category': 'General Finance',
            'description': 'Yahoo Finance news section',
            'active': True
        },
        {
            'name': 'CNBC Investing',
            'url': 'https://www.cnbc.com/investing/',
            'category': 'Business News',
            'description': 'CNBC investing section',
            'active': True
        },
        {
            'name': 'Reuters Business & Finance',
            'url': 'https://www.reuters.com/business/finance/',
            'category': 'Business News',
            'description': 'Reuters business and finance section',
            'active': True
        },
        {
            'name': 'Bloomberg Markets',
            'url': 'https://www.bloomberg.com/markets',
            'category': 'Markets',
            'description': 'Bloomberg markets section',
            'active': True
        },
        {
            'name': 'Seeking Alpha',
            'url': 'https://seekingalpha.com/',
            'category': 'Investment Analysis',
            'description': 'Investment research and analysis',
            'active': False
        },
        {
            'name': 'The Motley Fool',
            'url': 'https://www.fool.com/investing/',
            'category': 'Investment Advice',
            'description': 'Investment advice and stock analysis',
            'active': False
        }
    ]
    
    print("Setting up default news sources...")
    
    added_count = 0
    for source in default_sources:
        success = db.add_news_source(
            name=source['name'],
            url=source['url'],
            category=source['category'],
            description=source['description'],
            active=source['active']
        )
        
        if success:
            print(f"✓ Added: {source['name']}")
            added_count += 1
        else:
            print(f"⚠ Already exists: {source['name']}")
    
    print(f"\nSetup complete! Added {added_count} new sources.")
    
    # Show current sources
    sources = db.get_news_sources()
    active_sources = [s for s in sources if s.active]
    
    print(f"\nDatabase now contains:")
    print(f"  - Total sources: {len(sources)}")
    print(f"  - Active sources: {len(active_sources)}")
    print(f"  - Categories: {', '.join(db.get_categories())}")

if __name__ == "__main__":
    setup_default_sources()