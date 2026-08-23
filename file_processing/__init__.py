# file_processing/__init__.py
"""
File Processing Pipeline — Central module for storage optimization.

Every file uploaded to the system MUST pass through this pipeline.
This module enforces optimization by file type before storage.
"""
from file_processing.dispatcher import process_file, handle_upload

__all__ = ["process_file", "handle_upload"]
