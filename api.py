from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from proc.csv_import import create_database_engine


logger = logging.getLogger(__name__)
WEB_DIR = Path(__file__).resolve().parent / "web"
app = FastAPI(title="Network Log Analysis API")

ATTACKERS_QUERY = text(
    """
    SELECT
        host(addr) AS addr,
        n,
        latitude,
        longitude,
        country_name,
        city_name,
        asn,
        asn_organization,
        asn_network,
        lookup_status
    FROM logs.attackers
    """
)


@app.get("/api/attackers")
def get_attackers() -> list[dict[str, object]]:
    engine: Engine | None = None
    try:
        engine = create_database_engine()
        with engine.connect() as connection:
            rows = connection.execute(ATTACKERS_QUERY).mappings().all()
            return [dict(row) for row in rows]
    except (SQLAlchemyError, ValueError) as exc:
        logger.exception("Could not retrieve attacker records.")
        raise HTTPException(
            status_code=503,
            detail="Attacker data is currently unavailable.",
        ) from exc
    finally:
        if engine is not None:
            engine.dispose()


app.mount("/", StaticFiles(directory=WEB_DIR), name="web")
