# robots.txt check karne ke liye helpers

from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from .logger import setup_log

LOGGER = setup_log(__name__)
_ROBOTS_CACHE: dict[str, RobotFileParser] = {}

# URL se base domain nikalta hai
def _get_base_domain(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"

# Domain ke liye robots.txt parser lata hai (cache use karke)
def _get_robot_parser(base_domain: str) -> RobotFileParser | None:
    if base_domain in _ROBOTS_CACHE:
        return _ROBOTS_CACHE[base_domain]

    robots_url = f"{base_domain}/robots.txt"
    parser = RobotFileParser()
    parser.set_url(robots_url)

    try:
        parser.read()
        _ROBOTS_CACHE[base_domain] = parser
        return parser
    except Exception as e:
        LOGGER.warning("Could not read robots.txt from %s: %s", robots_url, e)
        return None

# Check karo ki URL crawl kar sakte hain ya nahi
def is_allowed(url: str, agent: str = "scraper_project/1.0") -> tuple[bool, str]:
    try:
        base = _get_base_domain(url)
        p = _get_robot_parser(base)

        if p is None:
            return True, ""

        ok = p.can_fetch(agent, url)
        if ok:
            return True, ""

        return False, f"Robots.txt disallowed access for agent '{agent}'"
    except Exception as e:
        LOGGER.warning("robots.txt check failed for %s: %s", url, e)
        return True, ""
