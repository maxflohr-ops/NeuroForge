"""Structured logging: JSON lines, one file per agent, mirrored to stderr."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "level": record.levelname.lower(),
            "msg": record.getMessage(),
        }
        extra = getattr(record, "data", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def get_logger(agent_name: str, log_dir: Path) -> logging.Logger:
    logger = logging.getLogger(f"fleet.{agent_name}")
    if logger.handlers:  # already configured
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False

    file_handler = logging.FileHandler(log_dir / f"{agent_name}.log", encoding="utf-8")
    file_handler.setFormatter(JsonLineFormatter())
    logger.addHandler(file_handler)

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(console)
    return logger


def log_event(logger: logging.Logger, msg: str, **data) -> None:
    logger.info(msg, extra={"data": data})
