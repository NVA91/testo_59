import logging
import logging.handlers
from pathlib import Path
from config.config import LOG_LEVEL, LOG_DIR

def setup_logging():
    """Logging konfigurieren"""
    logger = logging.getLogger()
    logger.setLevel(LOG_LEVEL)
    
    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(LOG_LEVEL)
    console_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File Handler
    log_file = LOG_DIR / "home_automation.log"
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=1000000, backupCount=5
    )
    file_handler.setLevel(LOG_LEVEL)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    return logger
