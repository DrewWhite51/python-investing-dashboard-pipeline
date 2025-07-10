#!/usr/bin/env python3
"""
Quick script to migrate existing summary JSON files to the database.
Includes duplicate detection to avoid inserting the same summaries twice.
"""

import os
import json
import glob
from datetime import datetime
from database import DatabaseManager

def migrate_summaries_to_database(summaries_dir="summaries", db_path="news_pipeline.db"):
    """Migrate all summary JSON files to the database with duplicate checking"""
    
    print("🚀 Starting Summary Migration to Database")
    print("=" * 50)
    
    # Initialize database manager
    db_manager = DatabaseManager(db_path)
    
    # Get initial count
    initial_count = db_manager.get_summaries_count()
    print(f"📊 Initial summaries in database: {initial_count}")
    
    # Find all summary JSON files
    json_pattern = os.path.join(summaries_dir, "summary_*.json")
    json_files = glob.glob(json_pattern)
    
    if not json_files:
        print(f"❌ No summary files found in {summaries_dir}")
        print(f"   Looking for pattern: {json_pattern}")
        return
    
    print(f"📁 Found {len(json_files)} summary files to process")
    
    # Counters
    success_count = 0
    duplicate_count = 0
    error_count = 0
    
    # Process each file
    for i, json_file in enumerate(json_files, 1):
        filename = os.path.basename(json_file)
        print(f"\n[{i:3d}/{len(json_files)}] Processing: {filename}")
        
        try:
            # Read the JSON file
            with open(json_file, 'r', encoding='utf-8') as f:
                summary_data = json.load(f)
            
            # Get source file for duplicate checking
            source_file = summary_data.get('source_file', filename)
            
            # Check if already exists
            if db_manager.check_summary_exists(source_file):
                print(f"    ⏭️  Already exists - skipping")
                duplicate_count += 1
                continue
            
            # Validate required fields
            if 'parsed_summary' not in summary_data:
                print(f"    ⚠️  Missing parsed_summary - skipping")
                error_count += 1
                continue
            
            # Add to database
            if db_manager.add_article_summary(summary_data):
                print(f"    ✅ Successfully added to database")
                success_count += 1
            else:
                print(f"    ❌ Failed to add to database")
                error_count += 1
                
        except json.JSONDecodeError as e:
            print(f"    ❌ JSON decode error: {e}")
            error_count += 1
        except FileNotFoundError:
            print(f"    ❌ File not found: {json_file}")
            error_count += 1
        except Exception as e:
            print(f"    ❌ Unexpected error: {e}")
            error_count += 1
    
    # Final summary
    final_count = db_manager.get_summaries_count()
    new_summaries = final_count - initial_count
    
    print("\n" + "=" * 50)
    print("📊 MIGRATION SUMMARY")
    print("=" * 50)
    print(f"📁 Files processed:        {len(json_files)}")
    print(f"✅ Successfully added:     {success_count}")
    print(f"⏭️  Skipped (duplicates):   {duplicate_count}")
    print(f"❌ Errors:                 {error_count}")
    print(f"📈 New summaries added:    {new_summaries}")
    print(f"📊 Total in database:      {final_count}")
    
    if success_count > 0:
        print(f"\n🎉 Migration completed successfully!")
    elif duplicate_count > 0:
        print(f"\n✨ All summaries already exist in database")
    else:
        print(f"\n⚠️  No summaries were added")

def check_database_status(db_path="news_pipeline.db"):
    """Check current database status"""
    print("🔍 Database Status Check")
    print("-" * 30)
    
    try:
        db_manager = DatabaseManager(db_path)
        
        # Check if table exists
        conn = db_manager.get_connection()
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='article_summaries'")
        table_exists = cursor.fetchone() is not None
        conn.close()
        
        if not table_exists:
            print("❌ article_summaries table does not exist")
            print("   Run database initialization first")
            return False
        
        # Get current count
        count = db_manager.get_summaries_count()
        print(f"✅ article_summaries table exists")
        print(f"📊 Current summaries: {count}")
        
        # Show sample data if any exists
        if count > 0:
            conn = db_manager.get_connection()
            cursor = conn.execute("SELECT source_file, processed_at, sentiment FROM article_summaries LIMIT 3")
            samples = cursor.fetchall()
            conn.close()
            
            print("\n📋 Sample records:")
            for row in samples:
                print(f"   • {os.path.basename(row[0])} | {row[1][:10]} | {row[2] or 'N/A'}")
        
        return True
        
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

def main():
    """Main migration script"""
    print("📦 Summary JSON to Database Migration Tool")
    print("=" * 60)
    
    # Check database status first
    if not check_database_status():
        print("\n❌ Database check failed. Please fix database issues first.")
        return
    
    print("\n" + "=" * 60)
    
    # Run migration
    try:
        migrate_summaries_to_database()
        
        print(f"\n✨ Migration complete! Check your database admin panel to verify.")
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        print("Please check your database configuration and try again.")

if __name__ == "__main__":
    main()