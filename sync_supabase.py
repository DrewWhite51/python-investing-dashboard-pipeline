#!/usr/bin/env python3
"""
SQLite to Supabase Sync Script
Syncs data from your SQLite news pipeline database to Supabase
"""

import sqlite3
import json
import hashlib
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import psycopg2
import psycopg2.extras
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class SyncConfig:
    sqlite_path: str
    postgres_connection_string: str
    batch_size: int = 100

class SQLiteSupabaseSync:
    def __init__(self, config: SyncConfig):
        self.config = config
        self.sync_state_file = '.sync_state.json'
        self.last_sync_hashes = self.load_sync_state()
        
        # Define tables in dependency order (tables with foreign keys come after their referenced tables)
        self.tables_to_sync = [
            'news_sources',
            'collection_batches', 
            'pipeline_runs',
            'collected_urls',
            'article_summaries'
        ]
    
    def get_postgres_connection(self):
        """Get PostgreSQL connection"""
        return psycopg2.connect(self.config.postgres_connection_string)
    
    def load_sync_state(self) -> Dict[str, str]:
        """Load last sync state from JSON file"""
        try:
            with open(self.sync_state_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
    
    def save_sync_state(self):
        """Save current sync state to JSON file"""
        with open(self.sync_state_file, 'w') as f:
            json.dump(self.last_sync_hashes, f, indent=2)
    
    def get_table_hash(self, table_name: str) -> str:
        """Generate hash of table data to detect changes"""
        conn = sqlite3.connect(self.config.sqlite_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            cursor.execute(f"SELECT * FROM {table_name} ORDER BY id")
            rows = [dict(row) for row in cursor.fetchall()]
            
            # Create hash of all data
            table_data = json.dumps(rows, sort_keys=True, default=str)
            table_hash = hashlib.md5(table_data.encode()).hexdigest()
            
            return table_hash
        except Exception as e:
            logger.error(f"Error getting hash for table {table_name}: {e}")
            return ""
        finally:
            conn.close()
    
    def has_table_changed(self, table_name: str) -> bool:
        """Check if table has changed since last sync"""
        current_hash = self.get_table_hash(table_name)
        last_hash = self.last_sync_hashes.get(table_name, "")
        return current_hash != last_hash
    
    def get_sqlite_table_data(self, table_name: str) -> List[Dict[str, Any]]:
        """Get all data from SQLite table"""
        conn = sqlite3.connect(self.config.sqlite_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            cursor.execute(f"SELECT * FROM {table_name}")
            rows = [dict(row) for row in cursor.fetchall()]
            return rows
        finally:
            conn.close()
    
    def clean_row_for_supabase(self, row: Dict[str, Any], table_name: str) -> Dict[str, Any]:
        """Clean row data for Supabase insertion"""
        cleaned_row = {}
        
        for key, value in row.items():
            # Convert boolean integers to actual booleans
            if table_name in ['news_sources', 'collection_batches', 'collected_urls', 'pipeline_runs']:
                if key in ['active', 'use_selenium', 'completed', 'used_in_pipeline']:
                    cleaned_row[key] = bool(value)
                else:
                    cleaned_row[key] = value
            else:
                cleaned_row[key] = value
        
        return cleaned_row
    
    def sync_table_full(self, table_name: str) -> bool:
        """Full sync of a table (delete all, insert all)"""
        try:
            logger.info(f"Starting full sync for table: {table_name}")
            
            # Get data from SQLite
            sqlite_data = self.get_sqlite_table_data(table_name)
            logger.info(f"Found {len(sqlite_data)} records in SQLite table {table_name}")
            
            if not sqlite_data:
                logger.info(f"No data to sync for table {table_name}")
                self.last_sync_hashes[table_name] = self.get_table_hash(table_name)
                return True
            
            # Clean data for PostgreSQL
            cleaned_data = [self.clean_row_for_supabase(row, table_name) for row in sqlite_data]
            
            # Connect to PostgreSQL
            pg_conn = self.get_postgres_connection()
            cursor = pg_conn.cursor()
            
            try:
                # Delete all existing data
                cursor.execute(f"DELETE FROM {table_name}")
                logger.info(f"Cleared existing data from table {table_name}")
                
                # Get column names from the first record
                if cleaned_data:
                    columns = list(cleaned_data[0].keys())
                    placeholders = ','.join(['%s'] * len(columns))
                    columns_str = ','.join(columns)
                    
                    insert_query = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"
                    
                    # Insert data in batches
                    total_inserted = 0
                    for i in range(0, len(cleaned_data), self.config.batch_size):
                        batch = cleaned_data[i:i + self.config.batch_size]
                        
                        # Convert batch to list of tuples
                        batch_values = [
                            tuple(row[col] for col in columns) 
                            for row in batch
                        ]
                        
                        psycopg2.extras.execute_batch(cursor, insert_query, batch_values)
                        total_inserted += len(batch)
                        logger.info(f"Inserted batch {i//self.config.batch_size + 1} for {table_name} ({len(batch)} records)")
                
                # Commit all changes
                pg_conn.commit()
                
                # Update sync hash
                self.last_sync_hashes[table_name] = self.get_table_hash(table_name)
                
                logger.info(f"Full sync completed for {table_name}: {total_inserted} records inserted")
                return True
                
            except Exception as e:
                pg_conn.rollback()
                logger.error(f"Error inserting data for {table_name}: {e}")
                return False
            finally:
                cursor.close()
                pg_conn.close()
                
        except Exception as e:
            logger.error(f"Error syncing table {table_name}: {e}")
            return False
    
    def create_tables_if_not_exist(self) -> bool:
        """Create tables in PostgreSQL if they don't exist"""
        try:
            logger.info("Creating tables if they don't exist...")
            
            pg_conn = self.get_postgres_connection()
            cursor = pg_conn.cursor()
            
            # Table creation SQL (converted from your SQLite schema)
            table_schemas = {
                'news_sources': '''
                    CREATE TABLE IF NOT EXISTS news_sources (
                        id BIGSERIAL PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE,
                        url TEXT NOT NULL UNIQUE,
                        category TEXT NOT NULL DEFAULT 'General',
                        description TEXT DEFAULT '',
                        active BOOLEAN NOT NULL DEFAULT true,
                        added_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        last_collected TIMESTAMP,
                        collection_count INTEGER NOT NULL DEFAULT 0,
                        avg_articles_found REAL NOT NULL DEFAULT 0.0
                    )
                ''',
                'collection_batches': '''
                    CREATE TABLE IF NOT EXISTS collection_batches (
                        id BIGSERIAL PRIMARY KEY,
                        batch_id TEXT NOT NULL UNIQUE,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        total_urls INTEGER NOT NULL DEFAULT 0,
                        sources_count INTEGER NOT NULL DEFAULT 0,
                        use_selenium BOOLEAN NOT NULL DEFAULT false,
                        completed BOOLEAN NOT NULL DEFAULT false,
                        error_message TEXT
                    )
                ''',
                'pipeline_runs': '''
                    CREATE TABLE IF NOT EXISTS pipeline_runs (
                        id BIGSERIAL PRIMARY KEY,
                        run_id TEXT NOT NULL UNIQUE,
                        started_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        completed_at TIMESTAMP,
                        status TEXT NOT NULL DEFAULT 'running',
                        urls_processed INTEGER NOT NULL DEFAULT 0,
                        summaries_generated INTEGER NOT NULL DEFAULT 0,
                        model_used TEXT,
                        use_selenium BOOLEAN NOT NULL DEFAULT false,
                        error_message TEXT
                    )
                ''',
                'collected_urls': '''
                    CREATE TABLE IF NOT EXISTS collected_urls (
                        id BIGSERIAL PRIMARY KEY,
                        source_id INTEGER NOT NULL,
                        url TEXT NOT NULL,
                        domain TEXT NOT NULL,
                        collected_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        collection_batch_id TEXT NOT NULL,
                        used_in_pipeline BOOLEAN NOT NULL DEFAULT false,
                        pipeline_run_id TEXT,
                        FOREIGN KEY (source_id) REFERENCES news_sources (id) ON DELETE CASCADE,
                        FOREIGN KEY (collection_batch_id) REFERENCES collection_batches (batch_id) ON DELETE CASCADE,
                        UNIQUE(url, collection_batch_id)
                    )
                ''',
                'article_summaries': '''
                    CREATE TABLE IF NOT EXISTS article_summaries (
                        id BIGSERIAL PRIMARY KEY,
                        source_file TEXT NOT NULL UNIQUE,
                        source_url TEXT,
                        processed_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        model_used TEXT NOT NULL,
                        raw_response TEXT NOT NULL,
                        summary TEXT,
                        investment_implications TEXT,
                        key_metrics TEXT,
                        companies_mentioned TEXT,
                        sectors_affected TEXT,
                        sentiment TEXT,
                        risk_factors TEXT,
                        opportunities TEXT,
                        time_horizon TEXT,
                        confidence_score REAL,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        pipeline_run_id TEXT,
                        url_id INTEGER,
                        FOREIGN KEY (pipeline_run_id) REFERENCES pipeline_runs (run_id) ON DELETE SET NULL,
                        FOREIGN KEY (url_id) REFERENCES collected_urls (id) ON DELETE SET NULL
                    )
                '''
            }
            
            # Create tables in dependency order
            for table_name in self.tables_to_sync:
                if table_name in table_schemas:
                    logger.info(f"Creating table: {table_name}")
                    cursor.execute(table_schemas[table_name])
            
            # Create indexes
            indexes = [
                'CREATE INDEX IF NOT EXISTS idx_collected_urls_source_id ON collected_urls(source_id)',
                'CREATE INDEX IF NOT EXISTS idx_collected_urls_batch_id ON collected_urls(collection_batch_id)',
                'CREATE INDEX IF NOT EXISTS idx_collected_urls_domain ON collected_urls(domain)',
                'CREATE INDEX IF NOT EXISTS idx_news_sources_active ON news_sources(active)',
                'CREATE INDEX IF NOT EXISTS idx_article_summaries_processed_at ON article_summaries(processed_at)',
                'CREATE INDEX IF NOT EXISTS idx_article_summaries_sentiment ON article_summaries(sentiment)',
                'CREATE INDEX IF NOT EXISTS idx_article_summaries_pipeline_run ON article_summaries(pipeline_run_id)',
                'CREATE INDEX IF NOT EXISTS idx_article_summaries_confidence ON article_summaries(confidence_score)',
                'CREATE INDEX IF NOT EXISTS idx_article_summaries_url ON article_summaries(source_url)'
            ]
            
            for index_sql in indexes:
                cursor.execute(index_sql)
            
            pg_conn.commit()
            cursor.close()
            pg_conn.close()
            
            logger.info("✅ Tables and indexes created successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error creating tables: {e}")
            return False

    def sync_all_tables(self, force: bool = False, create_tables: bool = True) -> Dict[str, bool]:
        """Sync all tables to Supabase"""
        results = {}
        
        logger.info("Starting sync process...")
        logger.info(f"Tables to sync: {self.tables_to_sync}")
        
        # Create tables first if requested
        if create_tables:
            if not self.create_tables_if_not_exist():
                logger.error("Failed to create tables, aborting sync")
                return {table: False for table in self.tables_to_sync}
        
        for table_name in self.tables_to_sync:
            if force or self.has_table_changed(table_name):
                if force:
                    logger.info(f"Force syncing table: {table_name}")
                else:
                    logger.info(f"Table {table_name} has changes, syncing...")
                
                results[table_name] = self.sync_table_full(table_name)
                
                if results[table_name]:
                    logger.info(f"✅ Successfully synced {table_name}")
                else:
                    logger.error(f"❌ Failed to sync {table_name}")
            else:
                logger.info(f"⏭️  No changes detected for {table_name}, skipping")
                results[table_name] = True  # Consider unchanged tables as successful
        
        # Save sync state
        self.save_sync_state()
        
        return results
    
    def verify_sync(self) -> Dict[str, Dict[str, int]]:
        """Verify sync by comparing record counts"""
        logger.info("Verifying sync...")
        verification_results = {}
        
        for table_name in self.tables_to_sync:
            # Get SQLite count
            conn = sqlite3.connect(self.config.sqlite_path)
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            sqlite_count = cursor.fetchone()[0]
            conn.close()
            
            # Get PostgreSQL count
            try:
                pg_conn = self.get_postgres_connection()
                cursor = pg_conn.cursor()
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                postgres_count = cursor.fetchone()[0]
                cursor.close()
                pg_conn.close()
            except Exception as e:
                logger.error(f"Error getting PostgreSQL count for {table_name}: {e}")
                postgres_count = -1
            
            verification_results[table_name] = {
                'sqlite_count': sqlite_count,
                'postgres_count': postgres_count,
                'match': sqlite_count == postgres_count
            }
            
            if sqlite_count == postgres_count:
                logger.info(f"✅ {table_name}: {sqlite_count} records (matching)")
            else:
                logger.warning(f"❌ {table_name}: SQLite={sqlite_count}, PostgreSQL={postgres_count}")
        
        return verification_results
    
    def print_summary(self, results: Dict[str, bool], verification: Dict[str, Dict[str, int]]):
        """Print sync summary"""
        print("\n" + "="*60)
        print("SYNC SUMMARY")
        print("="*60)
        
        successful_syncs = sum(1 for success in results.values() if success)
        total_syncs = len(results)
        
        print(f"Tables synced: {successful_syncs}/{total_syncs}")
        print("\nTable Details:")
        
        for table_name, success in results.items():
            status = "✅ SUCCESS" if success else "❌ FAILED"
            verification_info = verification.get(table_name, {})
            
            if verification_info and verification_info.get('match', False):
                count_info = f"({verification_info['sqlite_count']} records)"
            elif verification_info:
                count_info = f"(SQLite: {verification_info['sqlite_count']}, PostgreSQL: {verification_info['postgres_count']})"
            else:
                count_info = ""
            
            print(f"  {table_name}: {status} {count_info}")
        
        print("\n" + "="*60)

def main():
    """Main sync function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Sync SQLite database to PostgreSQL/Supabase')
    parser.add_argument('--sqlite-path', required=True, help='Path to SQLite database file')
    parser.add_argument('--postgres-url', required=True, help='PostgreSQL connection string')
    parser.add_argument('--force', action='store_true', help='Force sync all tables regardless of changes')
    parser.add_argument('--no-create-tables', action='store_true', help='Skip table creation (assume tables already exist)')
    parser.add_argument('--batch-size', type=int, default=100, help='Batch size for inserts')
    
    args = parser.parse_args()
    
    # Validate SQLite file exists
    if not os.path.exists(args.sqlite_path):
        logger.error(f"SQLite file not found: {args.sqlite_path}")
        return
    
    # Create sync configuration
    config = SyncConfig(
        sqlite_path=args.sqlite_path,
        postgres_connection_string=args.postgres_url,
        batch_size=args.batch_size
    )
    
    # Initialize sync service
    sync_service = SQLiteSupabaseSync(config)
    
    try:
        # Perform sync
        results = sync_service.sync_all_tables(force=args.force, create_tables=not args.no_create_tables)
        
        # Verify sync
        verification = sync_service.verify_sync()
        
        # Print summary
        sync_service.print_summary(results, verification)
        
        # Exit with error code if any syncs failed
        if not all(results.values()):
            exit(1)
            
    except Exception as e:
        logger.error(f"Sync failed with error: {e}")
        exit(1)

if __name__ == "__main__":
    main()