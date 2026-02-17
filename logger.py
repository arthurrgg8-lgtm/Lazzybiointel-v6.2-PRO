import json
import logging
from logging.handlers import TimedRotatingFileHandler   # CHANGED
from datetime import datetime

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # include extras if present
        for k, v in record.__dict__.items():
            if k.startswith("_") or k in (
                "name","msg","args","levelname","levelno","pathname","filename","module",
                "exc_info","exc_text","stack_info","lineno","funcName","created","msecs",
                "relativeCreated","thread","threadName","processName","process"
            ):
                continue
            payload[k] = v

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)

class LogManager:
    @staticmethod
    def get_logger(name: str = "lazzybiointel") -> logging.Logger:
        logger = logging.getLogger(name)
        if logger.handlers:
            return logger

        logger.setLevel(logging.INFO)

        # Daily rotation, keep 90 days (plan B)
        file_handler = TimedRotatingFileHandler(
            "face_verification.log",
            when="D",
            interval=1,
            backupCount=90,
            encoding="utf-8",
            utc=True,
        )
        file_handler.suffix = "%Y-%m-%d"   # produces face_verification.log.2026-01-02, etc.
        file_handler.setFormatter(JsonFormatter())

        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

        logger.addHandler(file_handler)
        logger.addHandler(console)
        logger.propagate = False
        return logger

