"""
Pihu — Structured Logger
Color-coded console output with module-tagged log entries.
"""

import logging
import sys
from pathlib import Path

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
except ImportError:
    # Fallback if colorama not installed
    class _Dummy:
        def __getattr__(self, _):
            return ""
    Fore = Style = _Dummy()


# ──────────────────────────────────────────────
# Color Map
# ──────────────────────────────────────────────
LEVEL_COLORS = {
    logging.DEBUG: Fore.CYAN,
    logging.INFO: Fore.GREEN,
    logging.WARNING: Fore.YELLOW,
    logging.ERROR: Fore.RED,
    logging.CRITICAL: Fore.MAGENTA,
}

MODULE_COLORS = {
    "STT": Fore.BLUE,
    "TTS": Fore.MAGENTA,
    "LLM": Fore.CYAN,
    "CLOUD": Fore.LIGHTCYAN_EX,
    "ROUTER": Fore.YELLOW,
    "INTENT": Fore.LIGHTYELLOW_EX,
    "MEMORY": Fore.GREEN,
    "SCHEDULER": Fore.LIGHTRED_EX,
    "AUDIO": Fore.LIGHTBLUE_EX,
    "BRAIN": Fore.LIGHTMAGENTA_EX,
    "TOOL": Fore.LIGHTGREEN_EX,
    "VISION": Fore.LIGHTWHITE_EX,
    "STREAM": Fore.LIGHTCYAN_EX,
    "MAIN": Fore.WHITE,
}


class PihuFormatter(logging.Formatter):
    """Custom formatter with colors and module tags."""

    FORMAT = "%(asctime)s | %(levelname)-8s | %(module_tag)s | %(message)s"
    DATE_FMT = "%H:%M:%S"

    def format(self, record):
        # Add module_tag if not present
        if not hasattr(record, "module_tag"):
            record.module_tag = "SYSTEM"

        # Colorize
        level_color = LEVEL_COLORS.get(record.levelno, "")
        module_color = MODULE_COLORS.get(record.module_tag, Fore.WHITE)

        record.levelname = f"{level_color}{record.levelname}{Style.RESET_ALL}"
        record.module_tag = f"{module_color}[{record.module_tag:^10}]{Style.RESET_ALL}"

        formatter = logging.Formatter(self.FORMAT, datefmt=self.DATE_FMT)
        return formatter.format(record)


class PihuLogger:
    """Factory for module-tagged loggers."""

    _initialized = False
    _root_logger = None

    @classmethod
    def _init_root(cls):
        if cls._initialized:
            return
            
        # Ensure stdout handles UTF-8 (emojis etc) especially on Windows
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding='utf-8')
            except Exception:
                pass

        cls._root_logger = logging.getLogger("pihu")
        cls._root_logger.setLevel(logging.DEBUG)

        # Console handler
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(logging.DEBUG)
        console.setFormatter(PihuFormatter())
        cls._root_logger.addHandler(console)

        # File handler (optional)
        try:
            from config import LOGS_DIR
            log_file = Path(LOGS_DIR) / "pihu.log"
            file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s | %(levelname)-8s | %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            cls._root_logger.addHandler(file_handler)
        except Exception:
            pass  # No file logging if config not available

        cls._initialized = True

    @classmethod
    def get(cls, module_tag: str) -> logging.LoggerAdapter:
        """Get a logger adapter with a module tag.
        
        Usage:
            log = PihuLogger.get("STT")
            log.info("Model loaded successfully")
        """
        cls._init_root()
        return logging.LoggerAdapter(
            cls._root_logger, {"module_tag": module_tag}
        )


# Convenience function
def get_logger(module_tag: str) -> logging.LoggerAdapter:
    """Shortcut: get_logger('STT')"""
    return PihuLogger.get(module_tag)
