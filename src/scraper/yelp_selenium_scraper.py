# src/scraper/yelp_selenium_scraper.py

import re
import time
import pandas as pd
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


def _init_driver(headless: bool = True):
    """Initialise un driver Chrome avec des options raisonnables."""
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver


def scrape_yelp_reviews_selenium(
    business_url: str,
    max_pages: int = 1,
    sleep_between: float = 2.0,
    headless: bool = True,
) -> pd.DataFrame:
    """
    Scrape UNIQUEMENT les textes d'avis Yelp pour une page business donnée.
    """

    driver = _init_driver(headless=headless)
    all_texts: list[str] = []

    try:
        for page in range(max_pages):
            start = page * 10
            sep = "&" if "?" in business_url else "?"
            url = f"{business_url}{sep}start={start}"

            print(f"Scraping page {page + 1} -> {url}")

            driver.get(url)
            time.sleep(sleep_between)

            html = driver.page_source
            soup = BeautifulSoup(html, "html.parser")

            # Les avis textuels sont dans des spans raw__09f24__xxx
            span_texts = soup.find_all("span", class_=re.compile(r"raw__09f24__"))
            print(f"  Nombre de spans trouvés : {len(span_texts)}")

            nb_added = 0
            for sp in span_texts:
                txt = sp.get_text(" ", strip=True)
                if not txt:
                    continue

                # garder uniquement de vrais avis : longueur minimale 80 caractères
                if len(txt) < 80:
                    continue

                all_texts.append(txt)
                nb_added += 1

            print(f"  Avis ajoutés sur cette page : {nb_added}")

            if nb_added == 0:
                break

    finally:
        driver.quit()

    df = pd.DataFrame({"Avis": all_texts})
    return df
