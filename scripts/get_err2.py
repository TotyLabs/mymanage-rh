import subprocess
res = subprocess.run(['alembic', 'upgrade', 'head'], capture_output=True, text=True)
with open('err.log', 'w', encoding='utf-8') as f:
    f.write(res.stderr)
