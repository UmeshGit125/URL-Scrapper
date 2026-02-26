# Scraper project ka main entry point

import csv
import json
import os
import random
import sys
import time

import certifi
import requests

from utils.logger import setup_log
from utils.parser import extract_structured_data, check_blocking
from utils.robots import is_allowed

# Logger setup
LOGGER = setup_log(__name__)

# Default URLs agar kuch na mile toh
DEFAULT_URLS: list[str] = [
    "https://theresanaiforthat.com/",
]

# URLs yahan resolve ho rahe hain - CLI, input ya default
def get_urls() -> list[str]:
    try:
        # Check command line args
        cli_urls = [arg.strip() for arg in sys.argv[1:] if arg.strip()]
        if cli_urls:
            LOGGER.info("Found %s URLs from command line.", len(cli_urls))
            return cli_urls

        # Agar command line khali hai toh user se pucho
        user_input = input(
            "Enter one or more URLs separated by commas (or press Enter for defaults): "
        ).strip()
        if user_input:
            input_urls = [url.strip() for url in user_input.split(",") if url.strip()]
            if input_urls:
                LOGGER.info("User provided %s URLs in prompt.", len(input_urls))
                return input_urls

        # Kuch nahi mila toh default list utha lo
        LOGGER.info("No URLs found. Using default URLs.")
        return DEFAULT_URLS
    except Exception as e:
        LOGGER.error("Error getting URLs, using defaults: %s", e)
        return DEFAULT_URLS

# Khali result object banata hai agar error aaye ya block ho jaye
def make_empty(url: str, status: str) -> dict:
    return {
        "url": url,
        "title": None,
        "h1": None,
        "meta_description": None,
        "rating": None,
        "review_count": None,
        "pricing": None,
        "ctas": [],
        "status": status,
    }

# URL se data fetch karne ka logic with retry
def fetch_url_data(url: str, tries: int = 3, wait: int = 2) -> requests.Response | None:
    # Retry codes: 429, 500, etc.
    retry_codes = {429, 500, 502, 503, 504}

    for i in range(tries + 1):
        try:
            response = requests.get(
                url,
                timeout=20,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"},
                verify=certifi.where(),
            )

            # Blocked toh nahi hain?
            response._was_blocked = check_blocking(response)

            if response._was_blocked:
                LOGGER.warning("Content appears blocked, skipping retry for: %s", url)
                return response

            if response.status_code == 403:
                LOGGER.warning("403 error for %s; skipping.", url)
                return response

            if response.status_code in retry_codes:
                if i < tries:
                    sleep_time = wait * (2**i)
                    LOGGER.warning(
                        "Retry %s/%s for %s. Waiting %ss (Status: %s)",
                        i + 1,
                        tries,
                        url,
                        sleep_time,
                        response.status_code,
                    )
                    time.sleep(sleep_time)
                    continue

                LOGGER.error("All retries exhausted for: %s", url)
                return None

            if response.status_code >= 400:
                LOGGER.error("HTTP %s error for %s", response.status_code, url)
                return None

            return response
        except Exception as e:
            if i < tries:
                sleep_time = wait * (2**i)
                LOGGER.warning(
                    "Error for %s: %s. Retry %s/%s after %ss",
                    url,
                    e,
                    i + 1,
                    tries,
                    sleep_time,
                )
                time.sleep(sleep_time)
                continue

            LOGGER.error("Request failed after %s retries for: %s", tries, url)
            return None

    return None

# Results ko JSON file mein save karo
def save_output_json(data: list[dict], path: str) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        LOGGER.info("JSON file created: %s", path)
    except Exception as e:
        LOGGER.error("Failed to write JSON output %s: %s", path, e)

# Results ko CSV file mein save karo
def save_output_csv(data: list[dict], path: str) -> None:
    fields = [
        "url", "title", "h1", "meta_description", "rating",
        "review_count", "pricing", "ctas_count", "status",
    ]

    try:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()

            for item in data:
                row = {
                    "url": item.get("url") or "",
                    "title": item.get("title") or "",
                    "h1": item.get("h1") or "",
                    "meta_description": item.get("meta_description") or "",
                    "rating": item.get("rating") or "",
                    "review_count": item.get("review_count") or "",
                    "pricing": item.get("pricing") or "",
                    "ctas_count": len(item.get("ctas") or []),
                    "status": item.get("status") or "",
                }
                writer.writerow(row)

        LOGGER.info("CSV file created: %s", path)
    except Exception as e:
        LOGGER.error("Failed to write CSV output %s: %s", path, e)

# Sari processing yahan se start hoti hai
def start_scraping(urls: list[str]) -> list[dict]:
    all_results = []

    for url in urls:
        LOGGER.info("Starting processing for: %s", url)
        try:
            # Check robots.txt
            allowed, reason = is_allowed(url)
            if not allowed:
                LOGGER.warning("Robots.txt disallowed: %s (Reason: %s)", url, reason)
                all_results.append(make_empty(url, "skipped"))
                continue

            # Thoda gap rakhein requests ke beech mein
            delay = random.uniform(2, 5)
            LOGGER.info("Waiting %.2fs for %s...", delay, url)
            time.sleep(delay)

            resp = fetch_url_data(url)
            if resp is None:
                all_results.append(make_empty(url, "failed"))
                continue

            # Check if blocked
            if getattr(resp, "_was_blocked", False):
                LOGGER.warning("Blocked content detected for %s", url)
                all_results.append(make_empty(url, "blocked"))
                continue

            if resp.status_code >= 400:
                LOGGER.error("Fetch failed for %s (Status: %s)", url, resp.status_code)
                all_results.append(make_empty(url, "failed"))
                continue

            # Data extract karo
            parsed_data = extract_structured_data(url, resp.text)
            all_results.append(parsed_data)
        except Exception as e:
            LOGGER.error("Unhandled error while processing %s: %s", url, e)
            all_results.append(make_empty(url, "failed"))

    return all_results

# Main function jo sab sambhalta hai
def main():
    try:
        # Output folder check karo
        base = os.path.dirname(os.path.abspath(__file__))
        output_path = os.path.join(base, "output")
        os.makedirs(output_path, exist_ok=True)

        # Kaam chalu karo
        urls_to_scrape = get_urls()
        results = start_scraping(urls_to_scrape)

        # Save results
        json_file = os.path.join(output_path, "results.json")
        csv_file = os.path.join(output_path, "results.csv")
        save_output_json(results, json_file)
        save_output_csv(results, csv_file)

        LOGGER.info("Processing completed for %s URLs.", len(results))
    except Exception as e:
        LOGGER.error("Fatal error in main: %s", e)

if __name__ == "__main__":
    main()
