import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

from bs4 import BeautifulSoup
import pandas as pd

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


REVIEWS_PER_PAGE = 10


def _init_driver(headless: bool) -> webdriver.Chrome:
    options = webdriver.ChromeOptions()

    if headless:
        options.add_argument("--headless=new")

    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")

    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    # anti-détection légère
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    # masquer webdriver
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            },
        )
    except Exception:
        pass

    return driver




def scrape_yelp_json(
    business_url: str,
    max_pages: int = 1,
    limit: int = 200,
    headless: bool = True,
    task_id: Optional[str] = None,
    results_dir: Optional[str] = None,
) -> Dict:
    """
    Scraping Yelp -> JSON compatible modèle
    """
    driver = _init_driver(headless=headless)
    results_path = Path(results_dir).resolve() if results_dir else None

    avis: List[Dict] = []
    numero = 1

    try:
        for page in range(max_pages):
            if numero > limit:
                break

            start = page * REVIEWS_PER_PAGE
            sep = "&" if "?" in business_url else "?"
            url = f"{business_url}{sep}start={start}"

            driver.get(url)
            time.sleep(3)

            # scroll (Yelp lazy-load)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.5)

            # wait minimal
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            except Exception:
                pass

            soup = BeautifulSoup(driver.page_source, "html.parser")
            blocks = soup.find_all("article")
            if not blocks:
                blocks = soup.find_all("li")

            added = 0

            for block in blocks:
                if numero > limit:
                    break

                # -------- TEXTE --------
                texts = []
                for tag in block.find_all(["p", "span"]):
                    t = tag.get_text(" ", strip=True)
                    if t and len(t) >= 80:
                        texts.append(t)

                if not texts:
                    continue

                contenu = max(texts, key=len).strip()

                # -------- AUTEUR --------
                profil = ""
                author_div = block.select_one('div[role="region"][aria-label]')
                if author_div:
                    profil = author_div.get("aria-label", "").strip()

                if not profil:
                    h4 = block.find("h4")
                    if h4:
                        profil = h4.get_text(" ", strip=True)

                # -------- DATE --------
                date = ""
                time_tag = block.find("time")
                if time_tag:
                    date = time_tag.get("datetime") or time_tag.get_text(" ", strip=True)
                else:
                    for sp in block.find_all("span"):
                        txt = sp.get_text(" ", strip=True)
                        if re.search(r"\b(19|20)\d{2}\b", txt) and len(txt) <= 40:
                            date = txt
                            break

                avis.append(
                    {
                        "numero": numero,
                        "profil": profil,
                        "titre_review": "",
                        "etoiles": None,
                        "etoiles_valeur": None,
                        "date": date,
                        "contenu": contenu,
                    }
                )

                numero += 1
                added += 1

            if added == 0:
                break

    finally:
        if not headless:
            time.sleep(10)
        driver.quit()

    return {
        "type": "yelp",
        "source": "Yelp",
        "url": business_url,
        "date_extraction": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "nb_avis_extraits": len(avis),
        "avis": avis,
    }
