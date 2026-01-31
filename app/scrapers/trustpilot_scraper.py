import json
import re
from datetime import datetime
from typing import Optional, Any, Dict, List, Tuple
import requests
from bs4 import BeautifulSoup

from app.scrapers.json_normalizer import normalize_review, build_result_json

DATE_IN_TEXT_RE = re.compile(r"(\d{1,2}\s+\w+\.?\s+\d{4})")
TOTAL_REVIEWS_RE = re.compile(r"\bsur\s+(\d+)\b", re.IGNORECASE)

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

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
    if not date_str:
        return date_str
    s = date_str.lower()
    for fr, en in FRENCH_MONTHS.items():
        s = s.replace(fr, en.lower())
    parts = s.split()
    if len(parts) == 3:
        day, month, year = parts
        return f"{day} {month.capitalize()} {year}"
    return s


def parse_date_french_to_yyyy_mm_dd(date_str: str) -> str:
    """
    Retourne 'YYYY-MM-DD' ou '' si impossible.
    Accepte ISO datetime (2025-12-09T...) ou FR (9 déc. 2025).
    """
    if not date_str:
        return ""

    s = str(date_str).replace("Date de l'expérience:", "").strip()

    # ISO first
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.date().isoformat()
    except Exception:
        pass

    # fallback: extrait une date "9 déc. 2025"
    m = DATE_IN_TEXT_RE.search(s)
    if m:
        s = m.group(1)

    try:
        normalized = translate_french_date(s)
        dt = datetime.strptime(normalized, "%d %B %Y")
        return dt.date().isoformat()
    except Exception:
        return ""


def get_total_pages(base_url: str) -> int:
    r = requests.get(base_url, timeout=20, headers=REQUEST_HEADERS)
    if r.status_code != 200:
        return 1
    soup = BeautifulSoup(r.text, "html.parser")

    last_page_element = soup.find("a", attrs={"name": "pagination-button-last"})
    if last_page_element:
        span_element = last_page_element.find("span")
        if span_element:
            try:
                return int(span_element.get_text(strip=True))
            except ValueError:
                pass

    txt = soup.get_text(" ", strip=True)
    m = TOTAL_REVIEWS_RE.search(txt)
    if m:
        try:
            total_reviews = int(m.group(1))
            per_page = 20
            return max(1, (total_reviews + per_page - 1) // per_page)
        except ValueError:
            pass

    return 1


def _clean_title(title: str) -> str:
    if not title:
        return ""
    t = title.strip()
    lower = t.lower()
    idx_avis = lower.find(" avis ")
    if idx_avis != -1 and "•" in t[: idx_avis + 1]:
        t = t[idx_avis + len(" avis ") :].strip(" .!-")
    return t


def _clean_review_text(text: str) -> str:
    """
    Enlève les artefacts "… Voir plus" si on tombe sur un bloc tronqué.
    (On garde ce fallback, mais l’objectif est d’éviter ça via __NEXT_DATA__.)
    """
    if not text:
        return ""

    t = text.strip()

    # cas simple: "... Voir plus" en fin
    t = re.sub(r"\s*…?\s*Voir plus\s*$", "", t, flags=re.IGNORECASE).strip()

    # cas relou: "(e... Voir plus" / " (e... Voir plus" etc.
    t = re.sub(r"\s*\(?[^()]{0,30}\.\.\.\s*Voir plus\s*\)?\s*$", "", t, flags=re.IGNORECASE).strip()

    return t


def _walk(obj: Any):
    """Générateur qui traverse récursivement dict/list."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for it in obj:
            yield from _walk(it)


def _extract_reviews_from_next_data(soup: BeautifulSoup) -> List[Tuple[str, str, str, str, Optional[float]]]:
    """
    Essaie de récupérer les reviews depuis le JSON Next.js (__NEXT_DATA__).
    Retourne une liste de tuples: (author, title, text, date_raw, rating)
    """
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return []

    try:
        data = json.loads(script.string)
    except Exception:
        return []

    reviews: List[Tuple[str, str, str, str, Optional[float]]] = []

    # Heuristique: trouver des dicts qui ressemblent à une review
    for node in _walk(data):
        # on cherche des champs typiques
        # text/content + title + consumer + date/published
        if not isinstance(node, dict):
            continue

        text = node.get("text") or node.get("reviewText") or node.get("content")
        consumer = node.get("consumer") or node.get("consumerInformation") or node.get("user")
        title = node.get("title") or node.get("headline") or ""
        date_raw = node.get("publishedDate") or node.get("date") or node.get("createdAt") or node.get("created")
        rating = node.get("rating") or node.get("stars") or node.get("score")

        if not text or not consumer:
            continue

        # author
        author = ""
        if isinstance(consumer, dict):
            author = (
                consumer.get("displayName")
                or consumer.get("name")
                or consumer.get("consumerName")
                or ""
            )
        elif isinstance(consumer, str):
            author = consumer

        # rating normalize
        try:
            rating_val = float(rating) if rating is not None else None
        except Exception:
            rating_val = None

        reviews.append((author.strip(), _clean_title(str(title)), str(text).strip(), str(date_raw or ""), rating_val))

    # Dé-doublonnage simple (texte)
    seen = set()
    out = []
    for a, t, tx, d, r in reviews:
        key = re.sub(r"\s+", " ", tx).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append((a, t, tx, d, r))

    return out


def _extract_from_article_html(article) -> Optional[Tuple[str, str, str, str]]:
    """Fallback HTML (moins fiable)"""
    author = ""
    el = article.select_one('span[data-consumer-name-typography="true"]')
    if el:
        author = el.get_text(" ", strip=True)

    title_el = article.find(attrs={"data-service-review-title-typography": True}) or article.find("h2")
    title = _clean_title(title_el.get_text(" ", strip=True) if title_el else "")

    text_el = article.find(attrs={"data-service-review-text-typography": True})
    if not text_el:
        for p in article.find_all("p"):
            txt = p.get_text(" ", strip=True)
            if "date de l'expérience" not in txt.lower():
                text_el = p
                break
    if not text_el:
        return None

    review_text = _clean_review_text(text_el.get_text(" ", strip=True))

    time_el = article.find("time", attrs={"data-service-review-date-time-ago": "true"}) or article.find("time")
    date_raw = ""
    if time_el:
        date_raw = time_el.get("datetime") or time_el.get_text(" ", strip=True)

    date_clean = parse_date_french_to_yyyy_mm_dd(date_raw)
    return author, title, review_text, date_clean


def scrape_trustpilot_json(
    *,
    domain: str,
    lang: str = "fr",
    max_pages: Optional[int] = None,
    limit: int = 200,
) -> dict:
    base_url = f"https://fr.trustpilot.com/review/{domain}?languages={lang}&sort=recency"
    nb_pages = max_pages if max_pages is not None else get_total_pages(base_url)

    avis_out: List[Dict] = []
    numero = 1

    for page_number in range(1, nb_pages + 1):
        if len(avis_out) >= limit:
            break

        page_url = f"https://fr.trustpilot.com/review/{domain}?page={page_number}&languages={lang}&sort=recency"
        r = requests.get(page_url, timeout=20, headers=REQUEST_HEADERS)
        if r.status_code != 200:
            continue

        soup = BeautifulSoup(r.text, "html.parser")

        # ✅ 1) Try Next.js JSON (texte complet, pas de "Voir plus")
        next_reviews = _extract_reviews_from_next_data(soup)
        if next_reviews:
            for author, title, text, date_raw, rating in next_reviews:
                if len(avis_out) >= limit:
                    break

                # date
                date_clean = parse_date_french_to_yyyy_mm_dd(date_raw)

                avis_out.append(
                    normalize_review(
                        numero=numero,
                        profil=author,
                        titre_review=title,
                        contenu=text,
                        date=date_clean,
                        etoiles=None,
                        etoiles_valeur=rating,
                    )
                )
                numero += 1
            continue  # page suivante

        # ✅ 2) Fallback HTML
        articles = soup.find_all("article")
        for art in articles:
            if len(avis_out) >= limit:
                break

            parsed = _extract_from_article_html(art)
            if not parsed:
                continue

            author, title, review_text, date_clean = parsed

            # si encore tronqué => on skip (sinon tu pollues avec "... Voir plus")
            if "voir plus" in (review_text or "").lower():
                continue

            avis_out.append(
                normalize_review(
                    numero=numero,
                    profil=author,
                    titre_review=title,
                    contenu=review_text,
                    date=date_clean,
                    etoiles=None,
                    etoiles_valeur=None,
                )
            )
            numero += 1

    return build_result_json(
        source="trustpilot",
        url=base_url,
        titre=f"Trustpilot: {domain}",
        marque=domain,
        filtre_france=(lang == "fr"),
        limite_demandee=limit,
        nb_pages_scrapees=nb_pages,
        avis=avis_out,
    )
