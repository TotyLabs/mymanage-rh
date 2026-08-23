import subprocess
res = subprocess.run(['alembic', 'upgrade', 'head'], capture_output=True, text=True)
print("--- STDOUT ---")
print(res.stdout)
print("--- STDERR ---")
print(res.stderr)
