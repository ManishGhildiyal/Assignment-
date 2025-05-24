# run_scraper.py
from apscheduler.schedulers.blocking import BlockingScheduler # type: ignore
from scrape_events import scrape_events

scheduler = BlockingScheduler()
scheduler.add_job(scrape_events, 'interval', hours=24)  # Run daily
scheduler.start()