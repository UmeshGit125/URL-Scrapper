# Logging utilities for the scraping project - yahan se logs control hote hain

import logging

# Log format set kar rahe hain
_LOG_FORMAT: str = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"

# Logger set karne ka function
def setup_log(name: str) -> logging.Logger:
    l = logging.getLogger(name)
    l.setLevel(logging.INFO)

    if l.handlers:
        return l

    fmt = logging.Formatter(_LOG_FORMAT)

    # Console output
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    # File output
    fh = logging.FileHandler("scraper.log", encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)

    l.addHandler(ch)
    l.addHandler(fh)
    l.propagate = False

    return l
