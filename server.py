"""
server.py — Entry Point for YouCompare Payroll

Production:  Gunicorn + UvicornWorkers (multi-process, high throughput)
Development: Uvicorn direct (single process, auto-reload friendly)
"""

import os
import sys
from dotenv import load_dotenv
load_dotenv()

from payroll_core import logger

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    is_production = os.getenv("PRODUCTION", "false").lower() == "true"

    if is_production:
        # =====================================================================
        # PRODUCTION: Gunicorn + UvicornWorkers
        # =====================================================================
        # Gunicorn manages multiple worker processes, each running a full
        # async event loop via UvicornWorker. Config is in gunicorn.conf.py.
        logger.info("=" * 60)
        logger.info("PRODUCTION MODE — Starting Gunicorn")
        logger.info("=" * 60)

        gunicorn_conf = os.path.join(os.path.dirname(__file__), "gunicorn.conf.py")
        os.execvp(
            sys.executable,
            [
                sys.executable, "-m", "gunicorn",
                "-c", gunicorn_conf,
                "main:app",
            ]
        )
    else:
        # =====================================================================
        # DEVELOPMENT: Uvicorn direct
        # =====================================================================
        import uvicorn

        logger.info(f"DEVELOPMENT MODE — Starting Uvicorn on {host}:{port}")
        logger.info("For auto-reload: uvicorn main:app --reload --reload-dirs api,modules,services,models")

        uvicorn.run(
            "main:app",
            host=host,
            port=port,
            reload=False,
        )
