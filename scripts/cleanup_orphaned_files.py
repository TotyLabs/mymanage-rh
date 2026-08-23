"""
Cleanup script for orphaned temporary files.
Removes temporary files that were created but not properly deleted
(e.g., due to Windows file locking or process crashes).

Use cases:
- Scheduled cleanup via cron/Task Scheduler
- Manual cleanup after investigating permission issues
- Post-recovery maintenance

Example:
    python scripts/cleanup_orphaned_files.py --receipts --age-hours 24
"""

import os
import sys
import time
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path to import payroll_core
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from payroll_core import ALLOWED_STORAGE_DIR, logger


def cleanup_directory(dir_path: str, pattern: str, age_hours: int = 24, dry_run: bool = False) -> dict:
    """
    Removes files matching pattern that haven't been modified in age_hours.
    
    Args:
        dir_path: Directory to clean
        pattern: File pattern to match (e.g., '*.tmp', 'tmp*.pdf')
        age_hours: Remove files older than this many hours
        dry_run: If True, don't actually delete files
    
    Returns:
        Dict with cleanup stats
    """
    stats = {
        "scanned": 0,
        "deleted": 0,
        "failed": 0,
        "freed_bytes": 0,
    }
    
    if not os.path.exists(dir_path):
        logger.warning(f"cleanup.dir_not_found path={dir_path}")
        return stats
    
    cutoff_time = datetime.now() - timedelta(hours=age_hours)
    
    for entry in Path(dir_path).glob(pattern):
        if not entry.is_file():
            continue
        
        stats["scanned"] += 1
        
        # Check file age
        mtime = datetime.fromtimestamp(entry.stat().st_mtime)
        if mtime > cutoff_time:
            continue  # File is too recent, skip
        
        try:
            file_size = entry.stat().st_size
            
            if dry_run:
                logger.info(f"cleanup.would_delete path={entry} age_hours={age_hours} size_bytes={file_size}")
            else:
                entry.unlink()
                stats["deleted"] += 1
                stats["freed_bytes"] += file_size
                logger.info(f"cleanup.deleted path={entry} size_bytes={file_size}")
        except Exception as e:
            stats["failed"] += 1
            logger.warning(f"cleanup.failed path={entry} err={e}")
    
    return stats


def cleanup_orphaned_temp_files(dry_run: bool = False, age_hours: int = 24) -> None:
    """
    Removes orphaned temporary files from storage directories.
    Targets files that are likely temporary and old.
    """
    logger.info(f"cleanup.starting dry_run={dry_run} age_hours={age_hours}")
    
    total_stats = {
        "scanned": 0,
        "deleted": 0,
        "failed": 0,
        "freed_bytes": 0,
    }
    
    # Cleanup temporary files in receipt storage
    receipts_dir = os.path.join(ALLOWED_STORAGE_DIR, "receipts")
    logger.info(f"cleanup.phase pattern=*.tmp dir={receipts_dir}")
    stats = cleanup_directory(receipts_dir, "*.tmp", age_hours=age_hours, dry_run=dry_run)
    for key in total_stats:
        total_stats[key] += stats[key]
    
    # Also cleanup tmp-prefixed files (from tempfile.mkstemp)
    logger.info(f"cleanup.phase pattern=tmp*.pdf dir={receipts_dir}")
    stats = cleanup_directory(receipts_dir, "tmp*.pdf", age_hours=age_hours, dry_run=dry_run)
    for key in total_stats:
        total_stats[key] += stats[key]
    
    # Report results
    freed_mb = total_stats["freed_bytes"] / (1024 * 1024)
    logger.info(
        f"cleanup.complete scanned={total_stats['scanned']} "
        f"deleted={total_stats['deleted']} failed={total_stats['failed']} "
        f"freed_mb={freed_mb:.2f}"
    )
    
    return total_stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cleanup orphaned temporary files")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting"
    )
    parser.add_argument(
        "--age-hours",
        type=int,
        default=24,
        help="Delete files older than this many hours (default: 24)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)s | %(message)s"
    )
    
    stats = cleanup_orphaned_temp_files(dry_run=args.dry_run, age_hours=args.age_hours)
    
    # Exit with error code if there were failures
    sys.exit(1 if stats["failed"] > 0 else 0)
