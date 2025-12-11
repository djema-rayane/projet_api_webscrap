# src/scraper/trustpilot_scraper.py

import re
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime

DATE_IN_TEXT_RE = re.compile(r"(\d{1,2}\s+\w+\.?\s+\d{4})")


# =========================
#   FONCTIONS UTILITAIRES
# =========================

def get_total_pages(url: str) -> int:
    """
    Récupère le nombre total de pages d'avis à partir de l'URL Trustpilot.
    """
    r = requests.get(url)
    if r.status_code != 200:
        print(f"[WARN] get_total_pages: status {r.status_code}, on retourne 1")
        return 1

    soup = BeautifulSoup(r.text, "html.parser")
    last_page_element = soup.find("a", attrs={"name": "pagination-button-last"})
    if last_page_element:
        span_element = last_page_element.find(
            "span",
            class_="typography_heading-xxs__QKBS8 typography_appearance-inherit__D7XqR typography_disableResponsiveSizing__OuNP7",
        )
        if span_element:
            try:
                return int(span_element.text.strip())
            except ValueError:
                pass
    return 1


# Mois FR -> EN (pour parser les dates)
FRENCH_MONTHS = {
    "janvier": "January",
    "février": "February",
    "fevrier": "February",
    "mars": "March",
    "avril": "April",
    "mai": "May",
    "juin": "June",
    "juillet": "July",
    "août": "August",
    "aout": "August",
    "septembre": "September",
    "octobre": "October",
    "novembre": "November",
    "décembre": "December",
    "decembre": "December",
    # abréviations
    "janv.": "January",
    "févr.": "February",
    "fevr.": "February",
    "avr.": "April",
    "juil.": "July",
    "sept.": "September",
    "oct.": "October",
    "nov.": "November",
    "déc.": "December",
    "dec.": "December",
}


def translate_french_date(date_str: str) -> str:
    """
    Remplace les mois français par leurs équivalents anglais.
    Ex : '12 mars 2024' -> '12 March 2024'
    """
    if not date_str:
        return date_str

    s = date_str.lower()
    for fr, en in FRENCH_MONTHS.items():
        s = s.replace(fr, en.lower())

    parts = s.split()
    if len(parts) == 3:
        day, month, year = parts
        month = month.capitalize()
        return f"{day} {month} {year}"
    return s


def parse_date(date_str: str):
    """
    Convertit une date FR en objet datetime.
    Renvoie None si le parsing échoue.
    """
    if not date_str:
        return None

    try:
        normalized = translate_french_date(date_str)
        return datetime.strptime(normalized, "%d %B %Y")
    except Exception:
        return None


# =========================
#   SCRAPING DES AVIS
# =========================

def _clean_title(title: str) -> str:
    """
    Nettoie le titre :
      - enlève 'FR • 8 avis', 'BE • 1 avis', etc.
      - garde seulement la partie 'Très grande qualité de coton...'
    """
    if not title:
        return title

    t = title.strip()

    # Cherche 'avis' (profil) dans le début du titre
    lower = t.lower()
    idx_avis = lower.find(" avis ")
    if idx_avis != -1 and "•" in t[: idx_avis + 1]:
        # on coupe tout ce qu'il y a avant 'avis'
        t = t[idx_avis + len(" avis "):].strip(" .!-")

    return t


def _extract_from_article(article) -> tuple[str | None, str | None, str | None]:
    """
    Récupère (titre, texte, date) à partir d'un <article>.

    On essaie d'abord d'utiliser les attributs data-service-review-*
    (plus stables que les classes CSS), puis on a des fallbacks.
    """

    # ---------- Titre ----------
    title_el = article.find(attrs={"data-service-review-title-typography": True})
    if not title_el:
        title_el = article.find("h2")

    title = title_el.get_text(" ", strip=True) if title_el else ""

    # ---------- Texte ----------
    text_el = article.find(attrs={"data-service-review-text-typography": True})
    if not text_el:
        # fallback : on prend le premier <p> qui ne parle pas de 'Date de l'expérience'
        for p in article.find_all("p"):
            txt = p.get_text(" ", strip=True)
            if "date de l'expérience" not in txt.lower():
                text_el = p
                break

    if not text_el:
        # pas de texte = probablement pas un avis
        return None, None, None

    review_text = text_el.get_text(" ", strip=True)

    # ---------- Date ----------
    date_str = ""
    date_el = article.find(
        attrs={"data-service-review-date-of-experience-typography": True}
    )
    if date_el:
        date_str = date_el.get_text(" ", strip=True)
        date_str = date_str.replace("Date de l'expérience:", "").strip()
    else:
        # fallback : on cherche un <time> avec une année
        for t in article.find_all("time"):
            t_text = t.get_text(" ", strip=True)
            if re.search(r"\d{4}", t_text):
                date_str = t_text
        date_str = date_str.replace("Date de l'expérience:", "").strip()

    # Nettoyage final du titre
    title = _clean_title(title)

    return title, review_text, date_str


def scraping_avis_TP(domain: str, nb_pages: int, lang: str):
    """
    Scrape les avis Trustpilot pour un domaine donné.
    On ne dépend plus des classes CSS, on se base sur les attributs data-*
    et sur des fallbacks raisonnables.
    """
    titre_avis_list: list[str] = []
    avis_list: list[str] = []
    dates_list: list[str] = []

    for page_number in range(1, nb_pages + 1):
        page_url = (
            f"https://fr.trustpilot.com/review/{domain}"
            f"?page={page_number}&languages={lang}&sort=recency"
        )
        print(f"Scraping page {page_number} -> {page_url}")

        r = requests.get(page_url)
        if r.status_code != 200:
            print(f"  [WARN] status {r.status_code}, page ignorée")
            continue

        soup = BeautifulSoup(r.text, "html.parser")

        articles = soup.find_all("article")
        print(f"  Nombre d'articles trouvés : {len(articles)}")

        for art in articles:
            title, review_text, date_str = _extract_from_article(art)

            # On saute si ce n'est pas un avis exploitable
            if not review_text:
                continue

            titre_avis_list.append(title or "")
            avis_list.append(review_text)
            dates_list.append(date_str or "")

    return titre_avis_list, avis_list, dates_list


# =========================
#   PIPELINE COMPLÈTE
# =========================

def scrape_trustpilot_to_df(domain: str, lang: str = "fr", max_pages: int | None = None):
    """
    Pipeline complet :
      - récupère le nombre de pages
      - scrape les avis
      - nettoie le texte
      - convertit les dates
      - renvoie un DataFrame trié et dédoublonné
    """
    base_url = f"https://fr.trustpilot.com/review/{domain}?languages={lang}&sort=recency"
    nb_pages = get_total_pages(base_url)
    if max_pages is not None:
        nb_pages = min(nb_pages, max_pages)

    print(f"Nombre total de pages : {nb_pages}")

    titres, avis, dates = scraping_avis_TP(domain, nb_pages, lang)

    print("Taille titres :", len(titres))
    print("Taille avis   :", len(avis))
    print("Taille dates  :", len(dates))

    df = pd.DataFrame(
        {"Titre de l'avis": titres, "Avis": avis, "Date_str": dates}
    )

    # -------------------------------------------------
    # 1) On enlève les avis tronqués avec "Voir plus"
    # -------------------------------------------------
    df = df[~df["Avis"].str.contains("Voir plus", na=False)].copy()

    # -------------------------------------------------
    # 2) On nettoie Date_str : on garde uniquement "12 janv. 2025"
    #    même si la chaîne contient "Actualisé le ..."
    # -------------------------------------------------
    def extract_date_str(s: str) -> str:
        if not s:
            return ""
        m = DATE_IN_TEXT_RE.search(s)
        return m.group(1) if m else s

    df["Date_str"] = df["Date_str"].astype(str).apply(extract_date_str)

    # -------------------------------------------------
    # 3) Conversion en datetime
    # -------------------------------------------------
    df["Date"] = df["Date_str"].apply(parse_date)

    # -------------------------------------------------
    # 4) On dédoublonne :
    #    - on garde, pour chaque texte d'avis,
    #      la ligne qui a un titre non vide en priorité
    # -------------------------------------------------
        # 4) Dédoublonnage
    #    - on normalise le texte (on enlève les \n, espaces multiples…)
    #    - on garde, pour chaque avis normalisé, la ligne avec titre en priorité
    df["Avis_norm"] = (
        df["Avis"]
        .astype(str)
        .str.replace(r"\s+", " ", regex=True)  # remplace tous les espaces/blancs par un seul espace
        .str.strip()
    )

    df["has_title"] = df["Titre de l'avis"].fillna("").str.strip().ne("")

    df = (
        df.sort_values(
            by=["Avis_norm", "has_title", "Date"],
            ascending=[True, False, False]
        )
        .drop_duplicates(subset=["Avis_norm"])
        .drop(columns=["has_title", "Avis_norm"])
        .reset_index(drop=True)
    )


    # -------------------------------------------------
    # 5) Tri final du plus récent au plus ancien
    # -------------------------------------------------
    df = df.sort_values(by="Date", ascending=False, na_position="last").reset_index(
        drop=True
    )

    return df
