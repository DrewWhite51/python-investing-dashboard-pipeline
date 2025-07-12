#!/usr/bin/env python3
"""
SQLite database models for the investment news pipeline.
Handles news sources (base URLs) and collected article URLs.
"""

import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import os

@dataclass
class NewsSource:
    id: Optional[int]
    name: str
    url: str
    category: str
    description: str
    active: bool
    added_at: str
    last_collected: Optional[str] = None
    collection_count: int = 0
    avg_articles_found: float = 0.0

@dataclass
class CollectedURL:
    id: Optional[int]
    source_id: int
    url: str
    domain: str
    collected_at: str
    collection_batch_id: str
    used_in_pipeline: bool = False
    pipeline_run_id: Optional[str] = None

@dataclass
class CollectionBatch:
    id: Optional[int]
    batch_id: str
    created_at: str
    total_urls: int
    sources_count: int
    use_selenium: bool
    completed: bool
    error_message: Optional[str] = None

class DatabaseManager:
    def __init__(self, db_path="news_pipeline.db"):
        self.db_path = db_path
        self.init_database() # Uncomment to initialize database on first run
    
    def get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        return conn
    
    def init_database(self):
        """Initialize database with tables - Updated to include source_url column"""
        conn = self.get_connection()
        print("Initializing database...")
        try:
            # Create news sources table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS news_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    url TEXT NOT NULL UNIQUE,
                    category TEXT NOT NULL DEFAULT 'General',
                    description TEXT DEFAULT '',
                    active BOOLEAN NOT NULL DEFAULT 1,
                    added_at TEXT NOT NULL DEFAULT (datetime('now')),
                    last_collected TEXT,
                    collection_count INTEGER NOT NULL DEFAULT 0,
                    avg_articles_found REAL NOT NULL DEFAULT 0.0
                )
            ''')
            
            # Create collection batches table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS collection_batches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_id TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    total_urls INTEGER NOT NULL DEFAULT 0,
                    sources_count INTEGER NOT NULL DEFAULT 0,
                    use_selenium BOOLEAN NOT NULL DEFAULT 0,
                    completed BOOLEAN NOT NULL DEFAULT 0,
                    error_message TEXT
                )
            ''')
            
            # Create collected URLs table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS collected_urls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id INTEGER NOT NULL,
                    url TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    collected_at TEXT NOT NULL DEFAULT (datetime('now')),
                    collection_batch_id TEXT NOT NULL,
                    used_in_pipeline BOOLEAN NOT NULL DEFAULT 0,
                    pipeline_run_id TEXT,
                    FOREIGN KEY (source_id) REFERENCES news_sources (id) ON DELETE CASCADE,
                    FOREIGN KEY (collection_batch_id) REFERENCES collection_batches (batch_id) ON DELETE CASCADE,
                    UNIQUE(url, collection_batch_id)
                )
            ''')
            
            # Create pipeline runs table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL UNIQUE,
                    started_at TEXT NOT NULL DEFAULT (datetime('now')),
                    completed_at TEXT,
                    status TEXT NOT NULL DEFAULT 'running',
                    urls_processed INTEGER NOT NULL DEFAULT 0,
                    summaries_generated INTEGER NOT NULL DEFAULT 0,
                    model_used TEXT,
                    use_selenium BOOLEAN NOT NULL DEFAULT 0,
                    error_message TEXT
                )
            ''')

            # Create article summaries table - UPDATED with source_url column
            conn.execute('''
                CREATE TABLE IF NOT EXISTS article_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_file TEXT NOT NULL,
                    source_url TEXT,
                    processed_at TEXT NOT NULL DEFAULT (datetime('now')),
                    model_used TEXT NOT NULL,
                    raw_response TEXT NOT NULL,
                    
                    -- Parsed summary fields
                    summary TEXT,
                    investment_implications TEXT,
                    key_metrics TEXT,  -- JSON array stored as text
                    companies_mentioned TEXT,  -- JSON array stored as text
                    sectors_affected TEXT,  -- JSON array stored as text
                    sentiment TEXT,
                    risk_factors TEXT,  -- JSON array stored as text
                    opportunities TEXT,  -- JSON array stored as text
                    time_horizon TEXT,
                    confidence_score REAL,
                    
                    -- Metadata
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    pipeline_run_id TEXT,
                    url_id INTEGER,
                    
                    FOREIGN KEY (pipeline_run_id) REFERENCES pipeline_runs (run_id) ON DELETE SET NULL,
                    FOREIGN KEY (url_id) REFERENCES collected_urls (id) ON DELETE SET NULL,
                    UNIQUE(source_file)
                )
            ''')
            
            # Create indexes for better performance
            conn.execute('CREATE INDEX IF NOT EXISTS idx_collected_urls_source_id ON collected_urls(source_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_collected_urls_batch_id ON collected_urls(collection_batch_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_collected_urls_domain ON collected_urls(domain)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_news_sources_active ON news_sources(active)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_article_summaries_processed_at ON article_summaries(processed_at)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_article_summaries_sentiment ON article_summaries(sentiment)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_article_summaries_pipeline_run ON article_summaries(pipeline_run_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_article_summaries_confidence ON article_summaries(confidence_score)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_article_summaries_url ON article_summaries(source_url)')
            
            conn.commit()
            
            # Check if source_url column exists, if not add it
            try:
                conn.execute('SELECT source_url FROM article_summaries LIMIT 1')
            except:
                # Column doesn't exist, add it
                conn.execute('ALTER TABLE article_summaries ADD COLUMN source_url TEXT')
                conn.commit()
                print("Added source_url column to existing article_summaries table")
            
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def add_article_summary(self, summary_data: Dict) -> bool:
        """Add an article summary to the database - Updated to include source_url"""
        conn = self.get_connection()
        try:
            parsed = summary_data.get('parsed_summary', {})
            
            conn.execute('''
                INSERT OR REPLACE INTO article_summaries (
                    source_file, source_url, processed_at, model_used, raw_response,
                    summary, investment_implications, key_metrics, companies_mentioned,
                    sectors_affected, sentiment, risk_factors, opportunities,
                    time_horizon, confidence_score, pipeline_run_id, url_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                summary_data.get('source_file'),
                summary_data.get('source_url'),  # NEW: Add the actual URL
                summary_data.get('processed_at'),
                summary_data.get('model_used'),
                summary_data.get('raw_response'),
                parsed.get('summary'),
                parsed.get('investment_implications'),
                json.dumps(parsed.get('key_metrics', [])),  # Store as JSON string
                json.dumps(parsed.get('companies_mentioned', [])),
                json.dumps(parsed.get('sectors_affected', [])),
                parsed.get('sentiment'),
                json.dumps(parsed.get('risk_factors', [])),
                json.dumps(parsed.get('opportunities', [])),
                parsed.get('time_horizon'),
                parsed.get('confidence_score'),
                summary_data.get('pipeline_run_id'),
                summary_data.get('url_id')  # This will now be properly set
            ))
            conn.commit()
            return True
        except Exception as e:
            print(f"Error adding summary to database: {e}")
            return False
        finally:
            conn.close()
        
    def _migrate_existing_data(self, conn):
        """Migrate data from JSON files to database"""
        # Migrate news sources
        if os.path.exists('news_sources.json'):
            try:
                with open('news_sources.json', 'r') as f:
                    data = json.load(f)
                    sources = data.get('sources', [])
                    
                    for source in sources:
                        try:
                            conn.execute('''
                                INSERT OR IGNORE INTO news_sources 
                                (name, url, category, description, active, added_at, last_collected, collection_count, avg_articles_found)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                source['name'],
                                source['url'], 
                                source['category'],
                                source.get('description', ''),
                                source['active'],
                                source['added_at'],
                                source.get('last_collected'),
                                source.get('collection_count', 0),
                                source.get('avg_articles_found', 0.0)
                            ))
                        except sqlite3.IntegrityError:
                            # Source already exists, skip
                            pass
                    
                    conn.commit()
                    print("Migrated news sources from JSON to database")
                    
            except Exception as e:
                print(f"Error migrating news sources: {e}")
    
    def debug_database_info(self):
        """Debug database file information"""
        import os
        print(f"Database path: {self.db_path}")
        print(f"Absolute path: {os.path.abspath(self.db_path)}")
        print(f"File exists: {os.path.exists(self.db_path)}")
        if os.path.exists(self.db_path):
            print(f"File size: {os.path.getsize(self.db_path)} bytes")
            print(f"Modified: {datetime.fromtimestamp(os.path.getmtime(self.db_path))}")
        
        # Check tables in this specific database
        conn = self.get_connection()
        try:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            print(f"Tables in {self.db_path}: {tables}")
        finally:
            conn.close()
    
    def execute_any_query(self, query: str) -> Tuple[List[Dict], List[str], str]:
        """Execute any SQL query and return results with operation type"""
        conn = self.get_connection()
        try:
            cursor = conn.execute(query)
            
            # Determine operation type
            query_upper = query.upper().strip()
            if query_upper.startswith('SELECT'):
                columns = [description[0] for description in cursor.description] if cursor.description else []
                results = [dict(zip(columns, row)) for row in cursor.fetchall()]
                operation = 'SELECT'
            elif query_upper.startswith(('INSERT', 'UPDATE', 'DELETE')):
                conn.commit()
                results = []
                columns = []
                operation = f"{query_upper.split()[0]} - {cursor.rowcount} rows affected"
            else:
                conn.commit()
                results = []
                columns = []
                operation = 'DDL_OPERATION'
            
            return results, columns, operation
        finally:
            conn.close()

    def get_table_data(self, table_name: str, limit: int = 100) -> Tuple[List[Dict], List[str]]:
        """Get sample data from a specific table"""
        conn = self.get_connection()
        try:
            cursor = conn.execute(f"SELECT * FROM {table_name} LIMIT ?", (limit,))
            columns = [description[0] for description in cursor.description]
            results = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return results, columns
        finally:
            conn.close()
 
    # ===== NEWS SOURCES METHODS =====
    
    def add_news_source(self, name: str, url: str, category: str = "General", 
                       description: str = "", active: bool = True) -> bool:
        """Add a new news source"""
        conn = self.get_connection()
        try:
            conn.execute('''
                INSERT INTO news_sources (name, url, category, description, active)
                VALUES (?, ?, ?, ?, ?)
            ''', (name, url, category, description, active))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
    
    def get_news_sources(self, active_only: bool = False) -> List[NewsSource]:
        """Get news sources"""
        conn = self.get_connection()
        try:
            if active_only:
                cursor = conn.execute('SELECT * FROM news_sources WHERE active = 1 ORDER BY name')
            else:
                cursor = conn.execute('SELECT * FROM news_sources ORDER BY name')
            
            sources = []
            for row in cursor.fetchall():
                sources.append(NewsSource(
                    id=row['id'],
                    name=row['name'],
                    url=row['url'],
                    category=row['category'],
                    description=row['description'],
                    active=bool(row['active']),
                    added_at=row['added_at'],
                    last_collected=row['last_collected'],
                    collection_count=row['collection_count'],
                    avg_articles_found=row['avg_articles_found']
                ))
            return sources
        finally:
            conn.close()
    
    def get_news_source_by_id(self, source_id: int) -> Optional[NewsSource]:
        """Get a news source by ID"""
        conn = self.get_connection()
        try:
            cursor = conn.execute('SELECT * FROM news_sources WHERE id = ?', (source_id,))
            row = cursor.fetchone()
            if row:
                return NewsSource(
                    id=row['id'],
                    name=row['name'],
                    url=row['url'],
                    category=row['category'],
                    description=row['description'],
                    active=bool(row['active']),
                    added_at=row['added_at'],
                    last_collected=row['last_collected'],
                    collection_count=row['collection_count'],
                    avg_articles_found=row['avg_articles_found']
                )
            return None
        finally:
            conn.close()
    
    def update_news_source(self, source_id: int, **kwargs) -> bool:
        """Update a news source"""
        conn = self.get_connection()
        try:
            # Build dynamic update query
            set_clauses = []
            params = []
            
            for key, value in kwargs.items():
                if key in ['name', 'url', 'category', 'description', 'active', 'last_collected', 'collection_count', 'avg_articles_found']:
                    set_clauses.append(f"{key} = ?")
                    params.append(value)
            
            if not set_clauses:
                return False
            
            params.append(source_id)
            query = f"UPDATE news_sources SET {', '.join(set_clauses)} WHERE id = ?"
            
            cursor = conn.execute(query, params)
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    def delete_news_source(self, source_id: int) -> bool:
        """Delete a news source"""
        conn = self.get_connection()
        print(f"Deleting news source with ID: {source_id}")
        try:
            cursor = conn.execute('DELETE FROM news_sources WHERE id = ?', (source_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    def get_categories(self) -> List[str]:
        """Get all unique categories"""
        conn = self.get_connection()
        try:
            cursor = conn.execute('SELECT DISTINCT category FROM news_sources ORDER BY category')
            return [row['category'] for row in cursor.fetchall()]
        finally:
            conn.close()
    
    def update_collection_stats(self, source_id: int, articles_found: int):
        """Update collection statistics for a source"""
        conn = self.get_connection()
        try:
            # Get current stats
            cursor = conn.execute('SELECT collection_count, avg_articles_found FROM news_sources WHERE id = ?', (source_id,))
            row = cursor.fetchone()
            
            if row:
                current_count = row['collection_count']
                current_avg = row['avg_articles_found']
                
                new_count = current_count + 1
                if current_count == 0:
                    new_avg = articles_found
                else:
                    new_avg = (current_avg * current_count + articles_found) / new_count
                
                conn.execute('''
                    UPDATE news_sources 
                    SET collection_count = ?, avg_articles_found = ?, last_collected = datetime('now')
                    WHERE id = ?
                ''', (new_count, round(new_avg, 1), source_id))
                conn.commit()
        finally:
            conn.close()
    
    # ===== COLLECTION BATCHES METHODS =====
    
    def create_collection_batch(self, batch_id: str, sources_count: int, use_selenium: bool = False) -> bool:
        """Create a new collection batch"""
        conn = self.get_connection()
        try:
            conn.execute('''
                INSERT INTO collection_batches (batch_id, sources_count, use_selenium)
                VALUES (?, ?, ?)
            ''', (batch_id, sources_count, use_selenium))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
    
    def complete_collection_batch(self, batch_id: str, total_urls: int, error_message: str = None):
        """Mark a collection batch as completed"""
        conn = self.get_connection()
        try:
            conn.execute('''
                UPDATE collection_batches 
                SET completed = 1, total_urls = ?, error_message = ?
                WHERE batch_id = ?
            ''', (total_urls, error_message, batch_id))
            conn.commit()
        finally:
            conn.close()
    
    def get_collection_batches(self, limit: int = 50) -> List[CollectionBatch]:
        """Get collection batches"""
        conn = self.get_connection()
        try:
            cursor = conn.execute('''
                SELECT * FROM collection_batches 
                ORDER BY created_at DESC 
                LIMIT ?
            ''', (limit,))
            
            batches = []
            for row in cursor.fetchall():
                batches.append(CollectionBatch(
                    id=row['id'],
                    batch_id=row['batch_id'],
                    created_at=row['created_at'],
                    total_urls=row['total_urls'],
                    sources_count=row['sources_count'],
                    use_selenium=bool(row['use_selenium']),
                    completed=bool(row['completed']),
                    error_message=row['error_message']
                ))
            return batches
        finally:
            conn.close()
    
    # ===== COLLECTED URLS METHODS =====
    
    def add_collected_urls(self, urls_data: List[Dict], batch_id: str) -> int:
        """Add collected URLs to database"""
        conn = self.get_connection()
        try:
            added_count = 0
            for url_data in urls_data:
                try:
                    conn.execute('''
                        INSERT INTO collected_urls 
                        (source_id, url, domain, collection_batch_id)
                        VALUES (?, ?, ?, ?)
                    ''', (
                        url_data['source_id'],
                        url_data['url'],
                        url_data['domain'],
                        batch_id
                    ))
                    added_count += 1
                except sqlite3.IntegrityError:
                    # URL already exists in this batch, skip
                    pass
            
            conn.commit()
            return added_count
        finally:
            conn.close()
    
    def delete_collected_url(self, url: CollectedURL) -> bool:
        """Delete a collected URL"""
        conn = self.get_connection()
        try:
            cursor = conn.execute('DELETE FROM collected_urls WHERE id = ?', (url.id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_collected_urls(self, batch_id: str = None, source_id: int = None, 
                          limit: int = None, used_only: bool = False) -> List[CollectedURL]:
        """Get collected URLs"""
        conn = self.get_connection()
        try:
            query = 'SELECT * FROM collected_urls WHERE 1=1'
            params = []
            
            if batch_id:
                query += ' AND collection_batch_id = ?'
                params.append(batch_id)
            
            if source_id:
                query += ' AND source_id = ?'
                params.append(source_id)
            
            if used_only:
                query += ' AND used_in_pipeline = 1'
            
            query += ' ORDER BY collected_at DESC'
            
            if limit:
                query += ' LIMIT ?'
                params.append(limit)
            
            cursor = conn.execute(query, params)
            
            urls = []
            for row in cursor.fetchall():
                urls.append(CollectedURL(
                    id=row['id'],
                    source_id=row['source_id'],
                    url=row['url'],
                    domain=row['domain'],
                    collected_at=row['collected_at'],
                    collection_batch_id=row['collection_batch_id'],
                    used_in_pipeline=bool(row['used_in_pipeline']),
                    pipeline_run_id=row['pipeline_run_id']
                ))
            return urls
        finally:
            conn.close()
    
    def get_latest_collected_urls(self, limit: int = 1000) -> List[CollectedURL]:
        """Get the most recent collected URLs"""
        conn = self.get_connection()
        try:
            cursor = conn.execute('''
                SELECT cu.*, cb.created_at as batch_created_at
                FROM collected_urls cu
                JOIN collection_batches cb ON cu.collection_batch_id = cb.batch_id
                WHERE cb.completed = 1
                ORDER BY cb.created_at DESC, cu.collected_at DESC
                LIMIT ?
            ''', (limit,))
            
            urls = []
            for row in cursor.fetchall():
                urls.append(CollectedURL(
                    id=row['id'],
                    source_id=row['source_id'],
                    url=row['url'],
                    domain=row['domain'],
                    collected_at=row['collected_at'],
                    collection_batch_id=row['collection_batch_id'],
                    used_in_pipeline=bool(row['used_in_pipeline']),
                    pipeline_run_id=row['pipeline_run_id']
                ))
            return urls
        finally:
            conn.close()
    
    def mark_urls_used_in_pipeline(self, url_ids: List[int]):
        """Mark URLs as used in a pipeline run"""
        if not url_ids:
            return
        
        conn = self.get_connection()
        try:
            placeholders = ','.join(['?'] * len(url_ids))
            conn.execute(f'''
                UPDATE collected_urls 
                SET used_in_pipeline = 1
                WHERE id IN ({placeholders})
            ''', url_ids)
            conn.commit()
        finally:
            conn.close()
    
    def get_collection_stats(self) -> Dict:
        """Get collection statistics"""
        conn = self.get_connection()
        try:
            # Get basic stats
            cursor = conn.execute('''
                SELECT 
                    COUNT(*) as total_urls,
                    COUNT(DISTINCT domain) as unique_domains,
                    COUNT(DISTINCT source_id) as sources_used,
                    COUNT(DISTINCT collection_batch_id) as total_batches,
                    SUM(CASE WHEN used_in_pipeline = 1 THEN 1 ELSE 0 END) as urls_used
                FROM collected_urls
            ''')
            stats = dict(cursor.fetchone())
            
            # Get latest batch info
            cursor = conn.execute('''
                SELECT batch_id, created_at, total_urls 
                FROM collection_batches 
                WHERE completed = 1 
                ORDER BY created_at DESC 
                LIMIT 1
            ''')
            latest_batch = cursor.fetchone()
            if latest_batch:
                stats['latest_batch'] = dict(latest_batch)
            
            # Get top domains
            cursor = conn.execute('''
                SELECT domain, COUNT(*) as count 
                FROM collected_urls 
                GROUP BY domain 
                ORDER BY count DESC 
                LIMIT 10
            ''')
            stats['top_domains'] = [dict(row) for row in cursor.fetchall()]
            
            return stats
        finally:
            conn.close()
    
    def get_database_schema(self) -> Dict:
        """Get database schema information"""
        conn = self.get_connection()
        try:
            schema = {}
            
            # Get all tables
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = [row['name'] for row in cursor.fetchall()]
            
            for table in tables:
                # Get column information
                cursor = conn.execute(f"PRAGMA table_info({table})")
                columns = []
                for row in cursor.fetchall():
                    columns.append({
                        'name': row['name'],
                        'type': row['type'],
                        'pk': bool(row['pk']),
                        'fk': False  # We'll check for foreign keys separately
                    })
                
                # Get foreign key information
                cursor = conn.execute(f"PRAGMA foreign_key_list({table})")
                fk_columns = {row['from']: row['table'] for row in cursor.fetchall()}
                
                # Mark foreign key columns
                for column in columns:
                    if column['name'] in fk_columns:
                        column['fk'] = True
                        column['fk_table'] = fk_columns[column['name']]
                
                schema[table] = columns
            
            return schema
        finally:
            conn.close()
    
    def get_database_stats(self) -> Dict:
        """Get overall database statistics"""
        conn = self.get_connection()
        try:
            stats = {}
            
            # Count records in each table
            cursor = conn.execute("SELECT COUNT(*) FROM news_sources")
            stats['total_sources'] = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM collected_urls")
            stats['total_urls'] = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM collection_batches")
            stats['total_batches'] = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(DISTINCT domain) FROM collected_urls")
            stats['unique_domains'] = cursor.fetchone()[0]
            
            # Database file size
            try:
                stats['db_size'] = os.path.getsize(self.db_path)
            except:
                stats['db_size'] = 0
            
            return stats
        finally:
            conn.close()
    
    def execute_query(self, query: str) -> Tuple[List[Dict], List[str]]:
        """Execute a SELECT query and return results"""
        conn = self.get_connection()
        try:
            cursor = conn.execute(query)
            columns = [description[0] for description in cursor.description]
            results = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return results, columns
        finally:
            conn.close()
    
    # ===== PIPELINE RUNS METHODS =====
    
    def create_pipeline_run(self, run_id: str, model_used: str, use_selenium: bool = False) -> bool:
        """Create a new pipeline run record"""
        conn = self.get_connection()
        try:
            conn.execute('''
                INSERT INTO pipeline_runs (run_id, model_used, use_selenium)
                VALUES (?, ?, ?)
            ''', (run_id, model_used, use_selenium))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
    
    def complete_pipeline_run(self, run_id: str, status: str, urls_processed: int, 
                            summaries_generated: int, error_message: str = None):
        """Complete collection_batchesa pipeline run"""
        conn = self.get_connection()
        try:
            conn.execute('''
                UPDATE pipeline_runs 
                SET completed_at = datetime('now'), status = ?, urls_processed = ?, 
                    summaries_generated = ?, error_message = ?
                WHERE run_id = ?
            ''', (status, urls_processed, summaries_generated, error_message, run_id))
            conn.commit()
        finally:
            conn.close()


    def check_tables(self):
        """Check what tables exist"""
        conn = self.get_connection()
        try:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            print(f"Tables in database: {tables}")
            return tables
        finally:
            conn.close()

    def check_summary_exists(self, source_file: str) -> bool:
        """Check if a summary already exists in the database"""
        conn = self.get_connection()
        try:
            cursor = conn.execute('SELECT COUNT(*) FROM article_summaries WHERE source_file = ?', (source_file,))
            return cursor.fetchone()[0] > 0
        finally:
            conn.close()

    def add_article_summary(self, summary_data: Dict) -> bool:
        """Add an article summary to the database"""
        conn = self.get_connection()
        try:
            parsed = summary_data.get('parsed_summary', {})
            
            conn.execute('''
                INSERT OR REPLACE INTO article_summaries (
                    source_file, processed_at, model_used, raw_response,
                    summary, investment_implications, key_metrics, companies_mentioned,
                    sectors_affected, sentiment, risk_factors, opportunities,
                    time_horizon, confidence_score, pipeline_run_id, url_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                summary_data.get('source_file'),
                summary_data.get('processed_at'),
                summary_data.get('model_used'),
                summary_data.get('raw_response'),
                parsed.get('summary'),
                parsed.get('investment_implications'),
                json.dumps(parsed.get('key_metrics', [])),  # Store as JSON string
                json.dumps(parsed.get('companies_mentioned', [])),
                json.dumps(parsed.get('sectors_affected', [])),
                parsed.get('sentiment'),
                json.dumps(parsed.get('risk_factors', [])),
                json.dumps(parsed.get('opportunities', [])),
                parsed.get('time_horizon'),
                parsed.get('confidence_score'),
                summary_data.get('pipeline_run_id'),  # You may need to set this
                summary_data.get('url_id')  # You may need to set this
            ))
            conn.commit()
            return True
        except Exception as e:
            print(f"Error adding summary to database: {e}")
            return False
        finally:
            conn.close()

    def get_summaries_count(self) -> int:
        """Get count of summaries in database"""
        conn = self.get_connection()
        try:
            cursor = conn.execute('SELECT COUNT(*) FROM article_summaries')
            return cursor.fetchone()[0]
        finally:
            conn.close()

def main():
    """Example usage and testing"""
    db = DatabaseManager()
    
    # Add some test sources
    db.add_news_source("CoinDesk", "https://www.coindesk.com/", "Cryptocurrency", "Leading crypto news")
    db.add_news_source("MarketWatch", "https://www.marketwatch.com/investing", "Stock Market", "Market news")
    
    # Get sources
    sources = db.get_news_sources()
    print(f"Found {len(sources)} news sources:")
    for source in sources:
        print(f"  - {source.name}: {source.url}")
    
    print(f"Categories: {db.get_categories()}")


if __name__ == "__main__":
    main()