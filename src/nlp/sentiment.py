# src/nlp/sentiment.py

from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

# Modèle multilingue open-source (fr + en)
MODEL_NAME = "nlptown/bert-base-multilingual-uncased-sentiment"

# Chargement du tokenizer et du modèle
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)

# Le modèle sort des étoiles 1 à 5
# On remappe en : negative / neutral / positive
def analyze_sentiment(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        return "neutral"

    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        padding=True,
        max_length=256,
    )

    with torch.no_grad():
        outputs = model(**inputs)
        probs = torch.softmax(outputs.logits, dim=-1)
        label_id = int(torch.argmax(probs, dim=-1))  # 0..4

    stars = label_id + 1  # 1 à 5

    if stars <= 2:
        return "negative"
    elif stars == 3:
        return "neutral"
    else:
        return "positive"

