import json
from typing import List, Dict


def save_reviews(reviews: List[Dict], filename: str = "reviews_raw.json"):
    """Enregistre les avis dans un fichier JSON."""
    filepath = f"data/{filename}"

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(reviews, f, indent=4, ensure_ascii=False)

    print(f"[SAVE] {len(reviews)} avis sauvegardés dans {filepath}")

