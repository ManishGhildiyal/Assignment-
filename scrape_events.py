import requests
import re
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from app import Event, db, app
from urllib.parse import urljoin, unquote
import logging
import time
import os
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType

# Configure logging
logging.basicConfig(filename='scraper.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def create_driver():
    """Initialize and return a Chrome WebDriver with configured options."""
    try:
        options = webdriver.ChromeOptions()
        options.add_argument('--headless=chrome')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--blink-settings=imagesEnabled=true')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        driver = webdriver.Chrome(service=Service(ChromeDriverManager(chrome_type=ChromeType.GOOGLE).install()), options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        logging.info("WebDriver initialized successfully.")
        return driver
    except Exception as e:
        logging.error(f"Failed to create WebDriver: {e}")
        print(f"Failed to create WebDriver: {e}")
        return None

def scrape_events():
    url = "https://www.eventbrite.com.au/d/australia--sydney/events/"
    driver = create_driver()
    if not driver:
        logging.error("WebDriver not created, exiting scraper.")
        return

    max_retries = 3
    for attempt in range(max_retries):
        try:
            logging.info(f"Fetching URL (attempt {attempt + 1}/{max_retries}): {url}")
            driver.set_page_load_timeout(60)
            driver.get(url)

            max_scrolls = 10
            scroll_count = 0
            last_height = driver.execute_script("return document.body.scrollHeight")
            while scroll_count < max_scrolls:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    logging.info("No more events to load.")
                    break
                last_height = new_height
                scroll_count += 1
                logging.info(f"Scrolled {scroll_count}/{max_scrolls} times.")

            try:
                WebDriverWait(driver, 30).until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'div[class*="event-card"], div[class*="eds-event-card"], div[class*="card"]'))
                )
            except TimeoutException as e:
                logging.error(f"Timeout waiting for event cards: {e}")
                driver.save_screenshot(f"error_screenshot_{attempt + 1}.png")
                with open(f"error_page_{attempt + 1}.html", "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
                raise

            soup = BeautifulSoup(driver.page_source, 'html.parser')
            logging.info(f"Page source length: {len(driver.page_source)}")
            break
        except Exception as e:
            logging.error(f"Failed to fetch URL with Selenium (attempt {attempt + 1}): {e}", exc_info=True)
            print(f"Failed to fetch URL with Selenium (attempt {attempt + 1}): {e}")
            driver.save_screenshot(f"error_screenshot_{attempt + 1}.png")
            with open(f"error_page_{attempt + 1}.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            if attempt == max_retries - 1:
                logging.error("Max retries reached, exiting.")
                return
            time.sleep(5)
        finally:
            if driver:
                driver.quit()
                logging.info("WebDriver closed.")

    # Save page HTML for debugging
    if 'soup' in locals():
        with open('page.html', 'w', encoding='utf-8') as f:
            f.write(soup.prettify())

    events = []
    seen_urls = set()

    # Updated selector for event cards
    event_elements = soup.select('div[class*="event-card"], div[class*="eds-event-card"], div[class*="card"]')
    logging.info(f"Found {len(event_elements)} event elements with selectors.")
    print(f"Found {len(event_elements)} event elements with selectors.")

    for event_div in event_elements:
        try:
            # Event Name
            name_elem = event_div.select_one('h2, h3, [class*="title"]')
            name = name_elem.text.strip()[:80] if name_elem else "Untitled Event"

            # Date / Time
            date_elem = event_div.select_one('time, [class*="date"], [class*="time"]')
            date = date_elem.text.strip()[:120] if date_elem else "No date available"

            # Description
            desc_elem = event_div.select_one('[class*="description"], [class*="summary"], p:not([class*="availability"])')
            description = desc_elem.text.strip()[:200] if desc_elem else name

            # Location
            location_elem = event_div.select_one('[class*="location"], [class*="venue"], [class*="city"]')
            location = location_elem.text.strip()[:100] if location_elem else ""

            # Event URL
            url_elem = event_div.select_one('a[href]')
            event_url = urljoin(url, url_elem['href'])[:200] if url_elem and url_elem.get('href') else url

            # Image extraction
            image_url = None
            img_elem = event_div.select_one('img[class*="event-card__image"], img[class*="card-image"], img')
            if img_elem:
                src = img_elem.get('src')
                if src and not src.startswith('data:'):
                    image_url = urljoin(url, src)
                else:
                    src_lazy = img_elem.get('data-src') or img_elem.get('data-lazy')
                    if src_lazy:
                        image_url = urljoin(url, src_lazy)

            if not image_url:
                img_container = event_div.select_one('[style*="background-image"]')
                if img_container:
                    style = img_container.get('style', '')
                    match = re.search(r'background-image:\s*url\(["\']?(.*?)["\']?\)', style)
                    if match:
                        image_url = urljoin(url, match.group(1))

            if image_url and 'img.evbuc.com/https' in image_url:
                try:
                    decoded_part = unquote(image_url.split('img.evbuc.com/')[1])
                    image_url = decoded_part
                except Exception as e:
                    logging.warning(f"Failed to decode image URL: {e}")

            if not image_url:
                logging.info(f"No image found in card for event: {name}, trying detail page: {event_url}")
                detail_driver = create_driver()
                if detail_driver:
                    try:
                        detail_driver.get(event_url)
                        WebDriverWait(detail_driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, 'img[class*="event-image"], img[class*="hero-image"], img'))
                        )
                        detail_soup = BeautifulSoup(detail_driver.page_source, 'html.parser')
                        detail_img = detail_soup.select_one('img[class*="event-image"], img[class*="hero-image"], img')
                        if detail_img:
                            src = detail_img.get('src')
                            if src and not src.startswith('data:'):
                                image_url = urljoin(event_url, src)
                            else:
                                src_lazy = detail_img.get('data-src') or detail_img.get('data-lazy')
                                if src_lazy:
                                    image_url = urljoin(event_url, src_lazy)
                    except Exception as e:
                        logging.warning(f"Failed to fetch image from detail page for {name}: {e}")
                    finally:
                        detail_driver.quit()

            if not image_url:
                logging.warning(f"No valid image found for event: {name}, skipping")
                continue

            # Filter events for Sydney
            if "Sydney" not in name and "Sydney" not in description and "Sydney" not in location:
                logging.info(f"Skipping non-Sydney event: {name}")
                continue

            # Skip duplicate URLs
            if event_url in seen_urls:
                logging.info(f"Skipping duplicate event: {name}")
                continue

            seen_urls.add(event_url)

            events.append(Event(name=name, date=date, description=description, url=event_url, image_url=image_url))
            logging.info(f"Scraped event: {name} with image: {image_url}")
            print(f"Scraped event: {name} with image: {image_url}")

        except Exception as e:
            logging.warning(f"Error parsing event: {e}")
            print(f"Error parsing event: {e}")
            continue

    # Save events to DB
    with app.app_context():
        try:
            Event.query.delete()
            db.session.commit()
            db.session.bulk_save_objects(events)
            db.session.commit()
            logging.info(f"Successfully saved {len(events)} events to the database.")
            print(f"Successfully saved {len(events)} events to the database.")
        except Exception as e:
            logging.error(f"Database error: {e}")
            print(f"Database error: {e}")
            db.session.rollback()

if __name__ == '__main__':
    scrape_events()
