#!/usr/bin/env python3
"""
download_images.py

A script to download all images from a given HTTP(S) URL, including dynamically loaded content (e.g., Pinterest).
Stops scrolling once the Pinterest “More ideas” container appears, and skips any images within that section.

Collects both `src` and `srcset` URLs, aggregating images as they load during scroll.

Usage:
    python download_images.py <url> [--output-dir OUTPUT]

Requirements:
    pip install selenium webdriver-manager requests
"""
import argparse
import os
import time
import hashlib
import requests
from urllib.parse import urlparse

from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from webdriver_manager.firefox import GeckoDriverManager


def parse_args():
    parser = argparse.ArgumentParser(
        description="Download all images from a given URL, stopping at Pinterest's More ideas section and excluding it."
    )
    parser.add_argument(
        "url", type=str, help="The URL of the page to scrape images from."
    )
    parser.add_argument(
        "--output-dir", type=str, default="images",
        help="Directory to save images into (default: ./images)"
    )
    parser.add_argument(
        "--scroll-pause", type=float, default=2.0,
        help="Time to wait (in seconds) between scrolls (default: 2.0)"
    )
    return parser.parse_args()


def setup_driver():
    options = Options()
    options.add_argument("-headless")
    service = Service(GeckoDriverManager().install())
    return webdriver.Firefox(service=service, options=options)


def scroll_and_collect(driver, pause_time):
    """
    Scrolls down until the Pinterest "More ideas" container appears, collecting image URLs on the way.
    Returns a set of all discovered image URLs (src and srcset entries), excluding those inside the More ideas section.
    """
    collected = set()
    last_height = driver.execute_script("return document.body.scrollHeight")

    while True:
        # Scroll to bottom and wait
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(pause_time)

        # Collect images currently on page (excluding More ideas section)
        imgs = driver.find_elements("tag name", "img")
        for img in imgs:
            # Skip images inside the More ideas container
            if img.find_elements("xpath", "ancestor::*[@data-test-id='more-ideas-container']"):
                continue
            # Get src
            src = img.get_attribute("src")
            if src and src.startswith("http"):
                collected.add(src)
            # Get srcset entries
            srcset = img.get_attribute("srcset")
            if srcset:
                # srcset format: "url1 1x, url2 2x, ..."
                for entry in srcset.split(','):
                    url_part = entry.strip().split(' ')[0]
                    if url_part.startswith("http"):
                        collected.add(url_part)

        # Check for More ideas container
        try:
            if driver.find_elements("css selector", "[data-test-id='more-ideas-container']"):
                print("Detected 'More ideas' section. Stopping scroll.")
                break
        except Exception:
            pass

        # Check for end of page
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

    return collected


def sanitize_filename(url):
    hash_digest = hashlib.md5(url.encode("utf-8")).hexdigest()
    ext = os.path.splitext(urlparse(url).path)[1]
    if not ext or len(ext) > 5:
        ext = ".jpg"
    return f"{hash_digest}{ext}"


def download_images(image_urls, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    for img_url in sorted(image_urls):
        try:
            resp = requests.get(img_url, timeout=10)
            resp.raise_for_status()
            fname = sanitize_filename(img_url)
            path = os.path.join(output_dir, fname)
            with open(path, "wb") as f:
                f.write(resp.content)
            print(f"Downloaded: {img_url} -> {path}")
        except Exception as e:
            print(f"Failed: {img_url} ({e})")


def main():
    args = parse_args()
    driver = setup_driver()
    print(f"Loading {args.url}...")
    driver.get(args.url)

    print("Scrolling and collecting images until 'More ideas' appears...")
    urls = scroll_and_collect(driver, args.scroll_pause)
    driver.quit()

    print(f"Found {len(urls)} images. Downloading...")
    download_images(urls, args.output_dir)

if __name__ == "__main__":
    main()
