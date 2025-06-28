#!/usr/bin/env python3
"""
Cleanup script for the investment news pipeline.
Removes files from pipeline output directories with various options.
This script should be placed in the /scripts directory.
"""

import os
import glob
import shutil
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

class PipelineCleanup:
    def __init__(self):
        # Get the parent directory (assuming script is in /scripts)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.project_root = os.path.dirname(script_dir)
        
        # Default directories used by the pipeline (relative to project root)
        self.directories = {
            'scraped': os.path.join(self.project_root, 'scraped_html'),
            'cleaned': os.path.join(self.project_root, 'cleaned_text'), 
            'summaries': os.path.join(self.project_root, 'summaries')
        }
        
        # File patterns for each directory
        self.file_patterns = {
            'scraped': '*.html',
            'cleaned': 'clean_*.txt',
            'summaries': 'summary_*.json'
        }
    
    def get_files_in_directory(self, directory, pattern='*'):
        """Get all files matching pattern in directory"""
        if not os.path.exists(directory):
            return []
        
        file_pattern = os.path.join(directory, pattern)
        return glob.glob(file_pattern)
    
    def get_directory_info(self, directory):
        """Get information about files in directory"""
        if not os.path.exists(directory):
            return {
                'exists': False,
                'file_count': 0,
                'total_size': 0,
                'files': []
            }
        
        files = []
        total_size = 0
        
        for file_path in glob.glob(os.path.join(directory, '*')):
            if os.path.isfile(file_path):
                file_stat = os.stat(file_path)
                files.append({
                    'path': file_path,
                    'name': os.path.basename(file_path),
                    'size': file_stat.st_size,
                    'modified': datetime.fromtimestamp(file_stat.st_mtime)
                })
                total_size += file_stat.st_size
        
        return {
            'exists': True,
            'file_count': len(files),
            'total_size': total_size,
            'files': files
        }
    
    def format_size(self, size_bytes):
        """Format file size in human-readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    def show_directory_status(self, target_dirs=None):
        """Display current status of directories"""
        print("=" * 70)
        print("PIPELINE DIRECTORY STATUS")
        print("=" * 70)
        
        dirs_to_check = target_dirs or list(self.directories.keys())
        
        for dir_key in dirs_to_check:
            if dir_key not in self.directories:
                print(f"Unknown directory: {dir_key}")
                continue
                
            directory = self.directories[dir_key]
            info = self.get_directory_info(directory)
            
            print(f"\n📁 {dir_key.upper()} ({directory}):")
            
            if not info['exists']:
                print("   Directory does not exist")
                continue
            
            print(f"   Files: {info['file_count']}")
            print(f"   Total size: {self.format_size(info['total_size'])}")
            
            if info['files']:
                # Show newest and oldest files
                files_by_date = sorted(info['files'], key=lambda x: x['modified'])
                newest = files_by_date[-1]
                oldest = files_by_date[0]
                
                print(f"   Newest: {newest['name']} ({newest['modified'].strftime('%Y-%m-%d %H:%M')})")
                print(f"   Oldest: {oldest['name']} ({oldest['modified'].strftime('%Y-%m-%d %H:%M')})")
    
    def clean_directory(self, dir_key, dry_run=False, older_than_days=None, confirm=True):
        """Clean files from a specific directory"""
        if dir_key not in self.directories:
            print(f"Error: Unknown directory '{dir_key}'")
            return False
        
        directory = self.directories[dir_key]
        pattern = self.file_patterns.get(dir_key, '*')
        
        if not os.path.exists(directory):
            print(f"Directory {directory} does not exist")
            return True
        
        # Get files to delete
        all_files = self.get_files_in_directory(directory, pattern)
        files_to_delete = []
        
        # Filter by age if specified
        if older_than_days:
            cutoff_date = datetime.now() - timedelta(days=older_than_days)
            for file_path in all_files:
                file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                if file_mtime < cutoff_date:
                    files_to_delete.append(file_path)
        else:
            files_to_delete = all_files
        
        if not files_to_delete:
            print(f"No files to delete in {dir_key}")
            return True
        
        # Calculate total size
        total_size = sum(os.path.getsize(f) for f in files_to_delete)
        
        print(f"\n{'DRY RUN: ' if dry_run else ''}Cleaning {dir_key} directory:")
        print(f"  Directory: {directory}")
        print(f"  Files to delete: {len(files_to_delete)}")
        print(f"  Total size: {self.format_size(total_size)}")
        
        if older_than_days:
            print(f"  Criteria: Files older than {older_than_days} days")
        
        # Show some example files
        if files_to_delete:
            print(f"  Examples:")
            for file_path in files_to_delete[:3]:
                file_name = os.path.basename(file_path)
                file_size = self.format_size(os.path.getsize(file_path))
                print(f"    - {file_name} ({file_size})")
            
            if len(files_to_delete) > 3:
                print(f"    ... and {len(files_to_delete) - 3} more files")
        
        if dry_run:
            print("  [DRY RUN] No files were actually deleted")
            return True
        
        # Confirm deletion
        if confirm:
            response = input(f"\nProceed with deletion? (y/N): ").strip().lower()
            if response not in ['y', 'yes']:
                print("Deletion cancelled")
                return False
        
        # Delete files
        deleted_count = 0
        for file_path in files_to_delete:
            try:
                os.remove(file_path)
                deleted_count += 1
            except Exception as e:
                print(f"Error deleting {file_path}: {e}")
        
        print(f"Successfully deleted {deleted_count} files from {dir_key}")
        return True
    
    def clean_all_directories(self, dry_run=False, older_than_days=None, confirm=True):
        """Clean all pipeline directories"""
        print(f"{'DRY RUN: ' if dry_run else ''}Cleaning all pipeline directories")
        
        if confirm and not dry_run:
            print("\nThis will delete files from ALL pipeline directories:")
            for dir_key, directory in self.directories.items():
                info = self.get_directory_info(directory)
                if info['exists'] and info['file_count'] > 0:
                    print(f"  - {dir_key}: {info['file_count']} files ({self.format_size(info['total_size'])})")
            
            response = input("\nProceed with cleaning ALL directories? (y/N): ").strip().lower()
            if response not in ['y', 'yes']:
                print("Cleanup cancelled")
                return False
        
        success = True
        for dir_key in self.directories.keys():
            if not self.clean_directory(dir_key, dry_run=dry_run, older_than_days=older_than_days, confirm=False):
                success = False
        
        return success
    
    def clean_empty_directories(self, dry_run=False):
        """Remove empty directories"""
        print(f"{'DRY RUN: ' if dry_run else ''}Checking for empty directories")
        
        for dir_key, directory in self.directories.items():
            if os.path.exists(directory) and not os.listdir(directory):
                print(f"  Empty directory: {directory}")
                if not dry_run:
                    try:
                        os.rmdir(directory)
                        print(f"  Removed empty directory: {directory}")
                    except Exception as e:
                        print(f"  Error removing directory {directory}: {e}")


def main():
    """Main function with command line interface"""
    parser = argparse.ArgumentParser(
        description='Cleanup script for investment news pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cleanup.py --status                           # Show directory status
  python cleanup.py --clean scraped                    # Clean scraped HTML files
  python cleanup.py --clean-all                       # Clean all directories
  python cleanup.py --clean summaries --older-than 7  # Clean summaries older than 7 days
  python cleanup.py --clean-all --dry-run             # Preview what would be deleted
  python cleanup.py --clean-all --no-confirm          # Clean without confirmation
        """
    )
    
    # Main actions
    parser.add_argument('--status', action='store_true', 
                       help='Show current status of all directories')
    parser.add_argument('--clean', choices=['scraped', 'cleaned', 'summaries'],
                       help='Clean specific directory')
    parser.add_argument('--clean-all', action='store_true',
                       help='Clean all pipeline directories')
    parser.add_argument('--clean-empty', action='store_true',
                       help='Remove empty directories')
    
    # Options
    parser.add_argument('--older-than', type=int, metavar='DAYS',
                       help='Only delete files older than N days')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be deleted without actually deleting')
    parser.add_argument('--no-confirm', action='store_true',
                       help='Skip confirmation prompts')
    
    # Specific directories
    parser.add_argument('--dirs', nargs='+', choices=['scraped', 'cleaned', 'summaries'],
                       help='Target specific directories for status')
    
    args = parser.parse_args()
    
    # Validate arguments
    if not any([args.status, args.clean, args.clean_all, args.clean_empty]):
        parser.print_help()
        print("\nError: You must specify an action (--status, --clean, --clean-all, or --clean-empty)")
        sys.exit(1)
    
    # Initialize cleanup
    cleanup = PipelineCleanup()
    
    try:
        # Show status
        if args.status:
            cleanup.show_directory_status(args.dirs)
        
        # Clean specific directory
        if args.clean:
            cleanup.clean_directory(
                args.clean,
                dry_run=args.dry_run,
                older_than_days=args.older_than,
                confirm=not args.no_confirm
            )
        
        # Clean all directories
        if args.clean_all:
            cleanup.clean_all_directories(
                dry_run=args.dry_run,
                older_than_days=args.older_than,
                confirm=not args.no_confirm
            )
        
        # Clean empty directories
        if args.clean_empty:
            cleanup.clean_empty_directories(dry_run=args.dry_run)
    
    except KeyboardInterrupt:
        print("\nCleanup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error during cleanup: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()