# src/cleaning.py

import re
import unicodedata
from langdetect import detect, LangDetectException


def clean_text(text: str) -> str:
    """Nettoie un avis client Yelp / Trustpilot sans perdre le sens."""
    if not isinstance(text, str):
        return ""

    # Normalisation unicode
    text = unicodedata.normalize("NFKC", text)

    # Supprimer les emojis
    emoji_pattern = re.compile("[" 
        u"\U0001F600-\U0001F64F"
        u"\U0001F300-\U0001F5FF"
        u"\U0001F680-\U0001F6FF"
        u"\U0001F1E0-\U0001F1FF"
        "]+", flags=re.UNICODE)
    text = emoji_pattern.sub(" ", text)

    # Enlever les guillemets au début / à la fin
    text = text.strip()
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1].strip()

    # Remplacer les retours à la ligne par des espaces
    text = text.replace("\n", " ")

    # Supprimer les URLs
    text = re.sub(r"http\S+|www\.\S+", "", text)

    # Réduire les espaces multiples
    text = re.sub(r"\s+", " ", text).strip()

    return text


def detect_language(text: str) -> str:
    """Renvoie 'fr', 'en', ... ou 'unknown'."""
    try:
        return detect(text)
    except LangDetectException:
        return "unknown"
