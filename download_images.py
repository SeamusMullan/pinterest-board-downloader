#!/usr/bin/env python3
"""
download_images.py

A script to download all images from a given HTTP(S) URL, including dynamically loaded content (e.g., Pinterest).
Stops scrolling once the Pinterest "More ideas" container appears, and skips any images within that section.

Collects both `src` and `srcset` URLs, aggregating images as they load during scroll.

Usage:
    python download_images.py <url> [--output-dir OUTPUT] [--quality {high-only,prioritize-high,all}]

Requirements:
    pip install selenium webdriver-manager requests
"""
import argparse
import os
import time
import hashlib
import requests
from urllib.parse import urlparse
from collections import defaultdict

from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.common.exceptions import StaleElementReferenceException
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
    parser.add_argument(
        "--quality", type=str, choices=["high-only", "prioritize-high", "all"], 
        default="high-only",
        help="Image quality preference: 'high-only' = only download high quality (default), "
             "'prioritize-high' = try high quality first, fall back to low quality, "
             "'all' = download both high and low quality versions"
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
    Returns a dictionary with 'high' and 'low' quality image URLs mapped to their image identifiers.
    """
    # Use a dictionary to organize images by their identifier (hash of URL path)
    # Each identifier will have high and low quality URLs
    collected_images = defaultdict(lambda: {'high': set(), 'low': set()})
    last_height = driver.execute_script("return document.body.scrollHeight")

    while True:
        # Scroll to bottom and wait
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(pause_time)

        # Collect images currently on page (excluding More ideas section)
        imgs = driver.find_elements("tag name", "img")
        for img in imgs:
            try:
                # Skip images inside the More ideas container
                # Check if the element is inside a "More ideas" container with a safer approach
                in_more_ideas = False
                try:
                    in_more_ideas = img.find_elements("xpath", "ancestor::*[@data-test-id='more-ideas-container']")
                except StaleElementReferenceException:
                    # If the element is stale, skip it and move on
                    continue
                
                if in_more_ideas:
                    continue
                
                # Get src (considered lower quality)
                src = img.get_attribute("src")
                if src and src.startswith("http"):
                    # Generate an identifier for this image using the path part of the URL
                    img_id = hashlib.md5(urlparse(src).path.encode('utf-8')).hexdigest()
                    collected_images[img_id]['low'].add(src)
                    
                # Get srcset entries (higher quality versions)
                srcset = img.get_attribute("srcset")
                if srcset:
                    # srcset format: "url1 1x, url2 2x, ..."
                    highest_density = 0
                    highest_url = None
                    
                    for entry in srcset.split(','):
                        parts = entry.strip().split(' ')
                        url_part = parts[0]
                        
                        # Skip non-http URLs
                        if not url_part.startswith("http"):
                            continue
                            
                        # Parse density (e.g., "2x" -> 2.0)
                        try:
                            if len(parts) > 1 and parts[1].endswith('x'):
                                density = float(parts[1][:-1])
                                # Keep track of highest density URL
                                if density > highest_density:
                                    highest_density = density
                                    highest_url = url_part
                            else:
                                # If no density specified, treat as low quality
                                img_id = hashlib.md5(urlparse(url_part).path.encode('utf-8')).hexdigest()
                                collected_images[img_id]['low'].add(url_part)
                        except (ValueError, IndexError):
                            # If parsing fails, add to low quality
                            img_id = hashlib.md5(urlparse(url_part).path.encode('utf-8')).hexdigest()
                            collected_images[img_id]['low'].add(url_part)
                    
                    # Add the highest density URL to high quality set
                    if highest_url:
                        img_id = hashlib.md5(urlparse(highest_url).path.encode('utf-8')).hexdigest()
                        collected_images[img_id]['high'].add(highest_url)
                    
            except StaleElementReferenceException:
                # Element became stale, skip it and continue with the next one
                continue

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

    return collected_images


def sanitize_filename(url, quality=None):
    """Create a sanitized filename for an image URL, optionally adding quality indicator."""
    hash_digest = hashlib.md5(url.encode("utf-8")).hexdigest()
    ext = os.path.splitext(urlparse(url).path)[1]
    if not ext or len(ext) > 5:
        ext = ".jpg"
        
    if quality:
        return f"{hash_digest}_{quality}{ext}"
    return f"{hash_digest}{ext}"


def download_images(image_dict, output_dir, quality_pref):
    """
    Download images based on quality preference.
    
    Args:
        image_dict: Dictionary with image IDs mapping to 'high' and 'low' quality URL sets
        output_dir: Directory to save downloaded images
        quality_pref: One of 'high-only', 'prioritize-high', or 'all'
    """
    os.makedirs(output_dir, exist_ok=True)
    download_count = 0
    skipped_count = 0
    
    for img_id, quality_urls in image_dict.items():
        high_quality_urls = quality_urls['high']
        low_quality_urls = quality_urls['low']
        
        # Determine which URLs to download based on preference
        urls_to_download = []
        
        if quality_pref == 'high-only':
            if high_quality_urls:
                urls_to_download = [(list(high_quality_urls)[0], 'high')]
            else:
                skipped_count += 1
                continue
                
        elif quality_pref == 'prioritize-high':
            if high_quality_urls:
                urls_to_download = [(list(high_quality_urls)[0], 'high')]
            elif low_quality_urls:
                urls_to_download = [(list(low_quality_urls)[0], 'low')]
            else:
                skipped_count += 1
                continue
                
        elif quality_pref == 'all':
            if high_quality_urls:
                urls_to_download.append((list(high_quality_urls)[0], 'high'))
            if low_quality_urls:
                urls_to_download.append((list(low_quality_urls)[0], 'low'))
            if not urls_to_download:
                skipped_count += 1
                continue
        
        # Download the selected URLs
        for img_url, quality in urls_to_download:
            try:
                resp = requests.get(img_url, timeout=10)
                resp.raise_for_status()
                
                # Generate different filenames based on quality when downloading all
                if quality_pref == 'all':
                    fname = sanitize_filename(img_url, quality)
                else:
                    fname = sanitize_filename(img_url)
                    
                path = os.path.join(output_dir, fname)
                with open(path, "wb") as f:
                    f.write(resp.content)
                print(f"Downloaded: {img_url} -> {path} ({quality} quality)")
                download_count += 1
            except Exception as e:
                print(f"Failed: {img_url} ({e})")
    
    print(f"\nDownload summary: {download_count} images downloaded, {skipped_count} skipped based on quality preference")


def main():
    args = parse_args()
    driver = setup_driver()
    print(f"Loading {args.url}...")
    driver.get(args.url)

    print(f"Scrolling and collecting images until 'More ideas' appears...")
    print(f"Image quality preference: {args.quality}")
    image_dict = scroll_and_collect(driver, args.scroll_pause)
    driver.quit()

    # Count total images found
    high_count = sum(1 for img in image_dict.values() if img['high'])
    low_count = sum(1 for img in image_dict.values() if img['low'])
    print(f"Found {len(image_dict)} unique images ({high_count} high quality, {low_count} low quality)")
    
    print(f"Downloading with '{args.quality}' preference...")
    download_images(image_dict, args.output_dir, args.quality)

if __name__ == "__main__":
    main()
