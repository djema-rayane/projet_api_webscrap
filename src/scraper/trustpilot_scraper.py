import re
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
}


def scrape_trustpilot_page(url: str):
    """
    Scrape UNE page Trustpilot en se basant sur le TEXTE brut de la page.
    On repère les blocs d'avis autour de 'Image: Noté X sur 5 étoiles'.
    Retourne une liste de dicts {rating, title, text, date}.
    """
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        print(f"[ERREUR HTTP] {resp.status_code} sur {url}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    # On récupère tout le texte de la page, ligne par ligne
    raw_text = soup.get_text("\n", strip=True)
    lines = [l for l in raw_text.split("\n") if l.strip()]

    reviews = []

    for i, line in enumerate(lines):
        # Cherche les lignes du type "Image: Noté 5 sur 5 étoiles"
        m = re.search(r"Noté\s+(\d)\s+sur\s+5\s+étoiles", line)
        if not m:
            continue

        rating = int(m.group(1))

        # On va essayer de récupérer quelques infos juste après cette ligne
        title = ""
        text = ""
        date = ""

        j = i + 1

        # On saute les lignes "Sur invitation", "Avis spontané", etc.
        while j < len(lines) and (
            lines[j].startswith("Sur invitation")
            or lines[j].startswith("Avis spontané")
            or lines[j].startswith("Voir ")
        ):
            j += 1

        # La ligne suivante est souvent le titre dans un [xx†Titre…]
        if j < len(lines) and "†" in lines[j] and "Image:" not in lines[j]:
            title_line = lines[j]
            # On récupère ce qu'il y a après le dernier "†"
            try:
                title = title_line.split("†", 1)[1].rstrip("】")
            except Exception:
                title = title_line
            j += 1

        # La ligne suivante est le texte de l'avis (souvent)
        if j < len(lines):
            text = lines[j]
            j += 1

        # On essaie ensuite de trouver une date proche :
        # - soit "Il y a X ..."
        # - soit "7 décembre 2025", etc.
        for k in range(j, min(j + 5, len(lines))):
            if lines[k].startswith("Il y a "):
                date = lines[k]
                break
            if re.search(r"\d{1,2}\s+\w+\s+\d{4}", lines[k]):
                date = lines[k]
                break

        if text:
            reviews.append(
                {
                    "rating": rating,
                    "title": title,
                    "text": text,
                    "date": date,
                }
            )

    print(f"[DEBUG] Avis extraits via texte brut: {len(reviews)}")
    return reviews


if __name__ == "__main__":
    url = "https://fr.trustpilot.com/review/boursobank.com"
    r = scrape_trustpilot_page(url)
    print(f"Nombre d'avis récupérés : {len(r)}")
    for rev in r[:5]:
        print(rev)



