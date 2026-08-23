import os
import json

skips = ['node_modules', '.git', 'venv', '__pycache__', '.pytest_cache', '.env', '.mypy_cache', 'alembic', 'dist', 'build', '.gemini']

all_files = []
for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if not any(s in d for s in skips)]
    for file in files:
        if not any(s in file for s in skips):
            full_path = os.path.join(root, file).replace('.\\', '')
            if not any(s in full_path for s in skips):
                all_files.append(full_path)

with open('audit_files.json', 'w', encoding='utf-8') as f:
    json.dump(sorted(all_files), f, indent=2)
