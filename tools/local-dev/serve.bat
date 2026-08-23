@echo off
REM Serve the UI folder on port 8001 using Python 3 with correct MIME types
pushd %~dp0
python server.py
popd