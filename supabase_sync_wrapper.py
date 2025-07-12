#!/usr/bin/env python3
import os
from dotenv import load_dotenv
import subprocess
import sys

load_dotenv()

def run_sync(force=False):
    cmd = [
        'python', 'sync_supabase.py',
        '--sqlite-path', os.getenv('SQLITE_PATH'),
        '--postgres-url', os.getenv('DATABASE_URL'),
    ]
    
    if force:
        cmd.append('--force')
    
    subprocess.run(cmd)

if __name__ == "__main__":
    force = '--force' in sys.argv
    run_sync(force=force)