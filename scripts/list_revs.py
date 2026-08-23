from alembic.config import Config
from alembic.script import ScriptDirectory

config = Config("alembic.ini")
script = ScriptDirectory.from_config(config)

print("--- REVISIONS ---")
for rev in script.walk_revisions():
    doc = str(rev.doc).replace("\n", " ").replace("\r", "")
    print(f"{rev.revision} (down: {rev.down_revision}) - {doc}")
