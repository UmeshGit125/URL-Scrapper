# HTML fetching and parsing helpers - yahan data extract hoga

import json
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .logger import setup_log

LOGGER = setup_log(__name__)

# Block karne wale keywords
_BLOCK_KEYWORDS: tuple[str, ...] = (
    "captcha", "blocked", "access denied", "unusual traffic",
    "verify you are human", "bot detected", "rate limit",
)

# CTA (buttons) search karne ke liye list
_CTA_KEYWORDS: tuple[str, ...] = (
    "get", "start", "try", "sign", "buy", "free", "demo", "download", "join", "subscribe", "add",
)

# Check karo ki site ne block toh nahi kiya
def check_blocking(response: requests.Response) -> bool:
    try:
        if response.status_code in {403, 429, 503}:
            LOGGER.warning("Blocking status code detected: %s", response.status_code)
            return True

        body = response.text.lower()
        for k in _BLOCK_KEYWORDS:
            if k in body:
                LOGGER.warning("Blocking keyword found: '%s'", k)
                return True

        return False
    except Exception as e:
        LOGGER.error("Error during block detection: %s", e)
        return False

# Element se saaf-suthra text nikalta hai
def get_text_clean(element) -> str:
    try:
        if element is None:
            return ""
        return element.get_text(" ", strip=True)
    except Exception as e:
        LOGGER.warning("Could not extract text from element: %s", e)
        return ""

# JSON-LD blocks se data uthata hai
def get_json_ld(soup: BeautifulSoup) -> list[dict]:
    items: list[dict] = []

    try:
        scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
        for s in scripts:
            raw = s.string or s.get_text(strip=True)
            if not raw:
                continue

            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if isinstance(parsed, list):
                for obj in parsed:
                    if isinstance(obj, dict):
                        items.append(obj)
            elif isinstance(parsed, dict):
                if "@graph" in parsed and isinstance(parsed.get("@graph"), list):
                    for obj in parsed["@graph"]:
                        if isinstance(obj, dict):
                            items.append(obj)
                items.append(parsed)
    except Exception as e:
        LOGGER.warning("Error parsing JSON-LD blocks: %s", e)

    return items

# Nested JSON data se specific value nikalna
def read_json_data(objs: list[dict], path: tuple[str, ...]) -> str | None:
    try:
        for o in objs:
            curr = o
            valid = True
            for k in path:
                if isinstance(curr, dict) and k in curr:
                    curr = curr[k]
                else:
                    valid = False
                    break

            if valid and curr is not None:
                if isinstance(curr, (str, int, float)):
                    return str(curr)
    except Exception as e:
        LOGGER.warning("Error reading JSON data path %s: %s", path, e)

    return None

# Page ka title dhundo
def find_title(soup: BeautifulSoup) -> str | None:
    try:
        tag = soup.find("title")
        t = get_text_clean(tag)
        return t or None
    except Exception as e:
        LOGGER.warning("Title not found: %s", e)
        return None

# First H1 tag nikalna
def find_h1(soup: BeautifulSoup) -> str | None:
    try:
        tags = soup.find_all("h1")
        if len(tags) > 1:
            LOGGER.warning("Multiple <h1> tags found; using the first one.")
        if not tags:
            return None

        t = get_text_clean(tags[0])
        return t or None
    except Exception as e:
        LOGGER.warning("Error finding H1: %s", e)
        return None

# Meta description uthana
def find_meta(soup: BeautifulSoup) -> str | None:
    try:
        m = soup.find("meta", attrs={"name": "description"})
        if m and m.get("content"):
            c = str(m.get("content")).strip()
            return c or None
        return None
    except Exception as e:
        LOGGER.warning("Error getting meta description: %s", e)
        return None

# Rating ya Reviews dhundna DOM mein
def get_metric(soup: BeautifulSoup, type: str) -> str | None:
    try:
        # Keywords for matching classes
        keys = ("rating", "stars", "score") if type == "rating" else ("review", "count")
        item_prop = "ratingValue" if type == "rating" else "reviewCount"

        # Itemprop check
        match = soup.find(attrs={"itemprop": item_prop})
        if match:
            v = get_text_clean(match) or str(match.get("content", "")).strip()
            if v: return v

        # Aria-label check
        match = soup.find(attrs={"aria-label": lambda x: isinstance(x, str) and type in x.lower()})
        if match:
            v = get_text_clean(match)
            if v: return v

        # Class matching logic
        for e in soup.find_all(True, class_=True):
            cls_list = e.get("class")
            if not isinstance(cls_list, list): cls_list = [str(cls_list)]
            
            combined = " ".join(cls_list).lower()
            if any(k in combined for k in keys):
                # For stars like books.toscrape.com, text is often empty but class has the value
                v = get_text_clean(e)
                if not v and type == "rating":
                    # Kuch sites classes mein store karti hain value like 'star-rating Three'
                    return combined.replace("star-rating", "").strip().capitalize()
                if v: return v

        return None
    except Exception as e:
        LOGGER.warning("Error extracting %s: %s", type, e)
        return None

# Pricing nikalna elements se
def get_price(soup: BeautifulSoup) -> str | None:
    try:
        match = soup.find(attrs={"itemprop": "price"})
        if match:
            v = get_text_clean(match) or str(match.get("content", "")).strip()
            if v: return v

        for t in ("div", "span", "p", "li", "section", "a", "button"):
            for e in soup.find_all(t):
                classes = " ".join(e.get("class", [])) if isinstance(e.get("class"), list) else str(e.get("class", ""))
                eid = str(e.get("id", ""))
                both = f"{classes} {eid}".lower()

                if any(k in both for k in ("price", "pricing", "plan", "cost")):
                    v = get_text_clean(e)
                    if v: return v

        return None
    except Exception as e:
        LOGGER.warning("Error finding price: %s", e)
        return None

# Links aur buttons (CTAs) dhundna
def get_btns(soup: BeautifulSoup, url: str) -> list[dict[str, str]]:
    res: list[dict[str, str]] = []

    try:
        # Scan for links, buttons, and input submissions
        for e in soup.find_all(["a", "button", "input"]):
            # Text pick karte hain
            if e.name == "input":
                t = (e.get("value") or e.get("placeholder") or "").strip()
                if e.get("type") not in ("submit", "button") and not t:
                    continue
            else:
                t = get_text_clean(e)

            if not t: continue

            h = ""
            if e.name == "a":
                h = str(e.get("href", "")).strip()
                if h: h = urljoin(url, h)

            tt = t.lower()
            hh = h.lower()
            
            # Check keywords in text or link
            if any(k in tt or k in hh for k in _CTA_KEYWORDS):
                res.append({"text": t, "href": h})

    except Exception as e:
        LOGGER.warning("Error scanning for CTAs: %s", e)

    return res

# HTML se sara data extract karne ka main function
def extract_structured_data(url: str, html: str) -> dict:
    data: dict = {
        "url": url, "title": None, "h1": None, "meta_description": None,
        "rating": None, "review_count": None, "pricing": None, "ctas": [], "status": "ok",
    }

    try:
        soup = BeautifulSoup(html, "html.parser")

        data["title"] = find_title(soup)
        if data["title"] is None:
            LOGGER.warning("Title missing for %s", url)

        data["h1"] = find_h1(soup)
        if data["h1"] is None:
            LOGGER.warning("H1 missing for %s", url)

        data["meta_description"] = find_meta(soup)
        if data["meta_description"] is None:
            LOGGER.warning("Meta description missing for %s", url)

        objs = get_json_ld(soup)

        data["rating"] = get_metric(soup, "rating")
        if data["rating"] is None:
            data["rating"] = read_json_data(objs, ("aggregateRating", "ratingValue"))

        data["review_count"] = get_metric(soup, "review_count")
        if data["review_count"] is None:
            data["review_count"] = read_json_data(objs, ("aggregateRating", "reviewCount"))
        if data["review_count"] is None:
            data["review_count"] = read_json_data(objs, ("aggregateRating", "ratingCount"))

        data["pricing"] = get_price(soup)
        if data["pricing"] is None:
            data["pricing"] = read_json_data(objs, ("offers", "price"))

        data["ctas"] = get_btns(soup, url)

        return data
    except Exception as e:
        LOGGER.error("Parsing failed for %s: %s", url, e)
        data["status"] = "failed"
        return data


