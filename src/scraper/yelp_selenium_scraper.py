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
    Scrape les avis Yelp (texte + nom + date) pour une page business donnée.
    """
    driver = _init_driver(headless=headless)
    all_data = []

    try:
        for page in range(max_pages):
            start = page * 10
            sep = "&" if "?" in business_url else "?"
            url = f"{business_url}{sep}start={start}"

            print(f"Scraping page {page + 1} -> {url}")

            driver.get(url)
            time.sleep(sleep_between)

            soup = BeautifulSoup(driver.page_source, "html.parser")

            # Texte d'avis : span.raw__09f24__...
            span_texts = soup.find_all("span", class_=re.compile(r"raw__09f24__"))
            print(f"  Nombre de spans trouvés : {len(span_texts)}")

            nb_added = 0

            for sp in span_texts:
                txt = sp.get_text(" ", strip=True)
                if not txt or len(txt) < 80:
                    continue

                # 🔹 Remonter au conteneur "avis"
                review_block = sp.find_parent("li") or sp.find_parent("div")
                if not review_block:
                    continue

                # ✅ Nom : div[role="region"][aria-label]
                nom = None
                author_div = review_block.select_one('div[role="region"][aria-label]')
                if author_div:
                    nom = author_div.get("aria-label")

                # ✅ Date : sélecteur exact trouvé dans ton HTML
                date = None
                date_span = review_block.select_one("span.y-css-nju7ub")
                if date_span:
                    date = date_span.get_text(strip=True)
                else:
                    # fallback : <time> si un jour Yelp l'utilise
                    time_tag = review_block.find("time")
                    if time_tag:
                        date = time_tag.get("datetime") or time_tag.get_text(strip=True)
                    else:
                        # fallback ultime : une vraie date contenant une année (moins fiable)
                        candidates = review_block.find_all("span")
                        for c in candidates:
                            t = c.get_text(" ", strip=True)
                            if re.search(r"\b\d{4}\b", t) and len(t) <= 25:
                                date = t
                                break

                all_data.append(
                    {
                        "Nom": nom,
                        "Date": date,
                        "Avis": txt,
                    }
                )
                nb_added += 1

            print(f"  Avis ajoutés sur cette page : {nb_added}")

            if nb_added == 0:
                break

    finally:
        driver.quit()

    return pd.DataFrame(all_data)
