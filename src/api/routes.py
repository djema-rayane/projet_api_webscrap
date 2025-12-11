from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from src.utils.cleaning import clean_text, detect_language
from src.nlp.sentiment import analyze_sentiment
from src.nlp.response_generator import generate_reply, Tone  # Tone vient du fichier ci-dessus

router = APIRouter()


class AvisInput(BaseModel):
    avis: str
    platform: str | None = None
    brand: str | None = None
    tone: Tone = "formel"  # "formel" | "amical" | "empathique"


@router.post("/analyze")
def analyze_avis(payload: AvisInput):
    avis_clean = clean_text(payload.avis)
    langue = detect_language(avis_clean)
    sentiment = analyze_sentiment(avis_clean)

    return {
        "avis_clean": avis_clean,
        "langue": langue,
        "sentiment": sentiment,
        "tone": payload.tone,  # on renvoie aussi le ton demandé (optionnel mais sympa)
    }


@router.post("/reply")
def reply(payload: AvisInput):
    avis_clean = clean_text(payload.avis)
    langue = detect_language(avis_clean)
    sentiment = analyze_sentiment(avis_clean)

    reply_text = generate_reply(
        avis_clean,
        sentiment,
        langue,
        payload.platform,
        payload.brand,
        payload.tone,   # 👈 on passe le ton ici
    )

    return {
        "reply": reply_text
    }
