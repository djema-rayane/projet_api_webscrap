import re
import threading
from typing import Any, Dict, List, Tuple

import pandas as pd 
import torch
from transformers import (
    AutoModelForCausalLM,
    AutoModelForSequenceClassification,
    AutoTokenizer,
)
from transformers.modeling_utils import PreTrainedModel
from transformers.tokenization_utils_base import PreTrainedTokenizerBase

# Ignorer mypy pour langdetect (pas de stubs disponibles)
from langdetect import detect, LangDetectException  # type: ignore[import-untyped]


def _sanitize_for_csv(value: Any) -> Any:
    """
    Rend les champs texte "CSV-friendly" (évite l'effet multi-lignes dans les éditeurs).
    - remplace retours ligne par \\n
    - supprime tabs
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        return value
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = value.replace("\n", "\\n")
    value = value.replace("\t", " ")
    return value.strip()


def limit_sentences(text: str, max_sentences: int = 5) -> str:
    """
    Coupe le texte à max_sentences phrases complètes.
    Ne laisse jamais une phrase tronquée.
    """
    if not text:
        return text

    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    if len(sentences) <= max_sentences:
        return text.strip()

    return " ".join(sentences[:max_sentences]).strip()


def detect_lang_fr_en(text: str) -> str:
    """
    Détecte la langue FR/EN avec langdetect.
    Retourne "fr" par défaut si détection impossible.
    """
    if not text or not text.strip():
        return "fr"
    
    try:
        lang = detect(text)
        return lang if lang in ["fr", "en"] else "fr"
    except LangDetectException:
        return "fr"


class ReviewAnalysisAndResponsePipeline:
    """
    Pipeline complet: analyse de sentiment + génération de réponses automatiques
    """

    sentiment_tokenizer: PreTrainedTokenizerBase
    sentiment_model: PreTrainedModel
    response_tokenizer: PreTrainedTokenizerBase
    response_model: PreTrainedModel
    device: str

    def __init__(
        self,
        sentiment_model: str = "nlptown/bert-base-multilingual-uncased-sentiment",
        response_model: str = "mistralai/Mistral-7B-Instruct-v0.2",
        use_gpu: bool = True,
    ):
        self.device = "cuda" if use_gpu and torch.cuda.is_available() else "cpu"

        if use_gpu and not torch.cuda.is_available():
            print("GPU demandé mais non disponible, utilisation du CPU\n")

        print("=" * 70)
        print("INITIALISATION DU PIPELINE")
        print("=" * 70 + "\n")

        # 1) Modèle sentiment
        print(f"Chargement du modèle de sentiment: {sentiment_model}")
        self.sentiment_tokenizer = AutoTokenizer.from_pretrained(sentiment_model)  # type: ignore[assignment]
        self.sentiment_model = AutoModelForSequenceClassification.from_pretrained(sentiment_model)  # type: ignore[assignment]
        self.sentiment_model.to(self.device)
        print("Modèle de sentiment chargé\n")

        # 2) Modèle génération
        print(f"Chargement du modèle de génération: {response_model}")
        self.response_tokenizer = AutoTokenizer.from_pretrained(response_model)  # type: ignore[assignment]

        if self.device == "cuda":
            self.response_model = AutoModelForCausalLM.from_pretrained(  # type: ignore[assignment]
                response_model,
                torch_dtype=torch.float16,
                device_map={"": 0},
                low_cpu_mem_usage=True,
            )
            print("Modèle de génération chargé entièrement sur GPU:0")
        else:
            self.response_model = AutoModelForCausalLM.from_pretrained(  # type: ignore[assignment]
                response_model,
                torch_dtype=torch.float32,
                low_cpu_mem_usage=True,
            )
            self.response_model.to(self.device)
            print(f"Modèle de génération chargé sur {self.device.upper()}")

        print(f"\nDispositif utilisé: {self.device.upper()}")
        if self.device == "cuda":
            mem_allocated = torch.cuda.memory_allocated(0) / 1024**3
            mem_reserved = torch.cuda.memory_reserved(0) / 1024**3
            print(f"VRAM utilisée: {mem_allocated:.2f} GB / Réservée: {mem_reserved:.2f} GB\n")

    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        if not isinstance(text, str) or not text.strip():
            return {"sentiment": "neutral", "confidence": 0.0, "stars_predicted": 3}

        inputs = self.sentiment_tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self.sentiment_model(**inputs)  # type: ignore[operator]
            probs = torch.softmax(outputs.logits, dim=-1)
            label_id = int(torch.argmax(probs, dim=-1).item())
            confidence = float(probs[0][label_id].item())

        stars = label_id + 1
        sentiment = "negative" if stars <= 2 else ("neutral" if stars == 3 else "positive")

        return {
            "sentiment": sentiment,
            "confidence": round(confidence, 3),
            "stars_predicted": stars,
        }

    def generate_response(self, row: Dict[str, Any], max_length: int = 280) -> str:
        """
        Génère une réponse professionnelle bilingue (FR/EN) selon la langue détectée.
        Fix: évite les réponses trop courtes type "Monsieur X," sur sentiments négatifs.
        Fix: limite par phrases complètes (pas de phrase coupée).
        """
        nom = row.get("Nom", "") or ""
        titre_avis = row.get("Titre de l'avis", "") or ""
        avis = row.get("Avis", "") or ""
        produit = row.get("produit_titre_complet", "") or ""
        marque = row.get("brand", "") or ""
        sentiment = row.get("sentiment", "neutral") or "neutral"
        etoiles = row.get("etoiles_valeur")

        # Détection de la langue
        lang = detect_lang_fr_en(avis)
        
        # Configuration client
        if lang == "en":
            client_name = nom.strip() if isinstance(nom, str) and nom.strip() else "Dear Customer"
        else:
            client_name = nom.strip() if isinstance(nom, str) and nom.strip() else "Madame, Monsieur"

        if marque and marque != "Marque non disponible":
            marque_clean = str(marque).lower().replace(" ", "").replace("-", "")
            if lang == "en":
                email_service = f"{marque_clean}@customerservice.com"
            else:
                email_service = f"{marque_clean}@serviceclient.fr"
        else:
            if lang == "en":
                email_service = "support@customerservice.com"
            else:
                email_service = "support@serviceclient.fr"

        include_contact = sentiment != "positive"
        etoiles_text = f" ({etoiles}/5 stars)" if etoiles and lang == "en" else (f" ({etoiles}/5 étoiles)" if etoiles else "")

        # PROMPT FRANÇAIS
        if lang == "fr":
            prompt_lines = [
                "Vous êtes un agent de service client professionnel.",
                "",
                "Objectif:",
                "Rédiger une réponse professionnelle à un message client.",
                "",
                "Contraintes STRICTES:",
                "- Ton professionnel, sobre, courtois (pas familier)",
                "- Vouvoiement obligatoire",
                "- Ne pas commencer par Monsieur/Madame/Bonjour/Bonsoir",
                "- Pas d'emojis",
                "- Pas de flatterie (ex: bravo, excellent choix, etc.)",
                "- Pas de marketing ni de promesses",
                "- 3 à 5 phrases maximum",
                "- Ne pas mentionner Amazon ni le mot avis",
                "- Ne pas recopier le message du client mot pour mot",
                "- Répondre uniquement avec le texte final (pas de préambule)",
                "",
                "Contexte:",
                f"- Nom du client: {client_name}",
                f"- Produit: {produit}",
                f"- Marque: {marque}",
                f"- Sentiment: {sentiment}{etoiles_text}",
                f"- Titre: {titre_avis}",
                f"- Message client: {avis}",
            ]

            if include_contact:
                prompt_lines.append(f"- Contact SAV: {email_service}")

            prompt_lines += [
                "",
                "Consigne:",
                "- Si sentiment POSITIF: remercier brièvement et confirmer la prise en compte.",
                "- Si sentiment NEUTRE: remercier et proposer une aide si besoin.",
                "- Si sentiment NEGATIF: s'excuser et inviter à contacter le SAV.",
            ]

            if include_contact:
                prompt_lines.append(f"- Mentionner l'email SAV exactement: {email_service}")
            else:
                prompt_lines.append("- Ne pas mentionner d'email.")

            prompt_lines += ["", "Réponse:"]

        # PROMPT ANGLAIS
        else:
            prompt_lines = [
                "You are a professional customer service agent.",
                "",
                "Objective:",
                "Write a professional response to a customer message.",
                "",
                "STRICT Constraints:",
                "- Professional, sober, courteous tone (not casual)",
                "- Formal address (you/your)",
                "- Do not start with Dear/Hello/Hi",
                "- No emojis",
                "- No flattery (ex: great choice, excellent, etc.)",
                "- No marketing or promises",
                "- 3 to 5 sentences maximum",
                "- Do not mention Amazon or the word review",
                "- Do not copy the customer's message word for word",
                "- Respond only with the final text (no preamble)",
                "",
                "Context:",
                f"- Customer name: {client_name}",
                f"- Product: {produit}",
                f"- Brand: {marque}",
                f"- Sentiment: {sentiment}{etoiles_text}",
                f"- Title: {titre_avis}",
                f"- Customer message: {avis}",
            ]

            if include_contact:
                prompt_lines.append(f"- Customer service contact: {email_service}")

            prompt_lines += [
                "",
                "Instructions:",
                "- If sentiment POSITIVE: thank briefly and confirm acknowledgment.",
                "- If sentiment NEUTRAL: thank and offer help if needed.",
                "- If sentiment NEGATIVE: apologize and invite to contact customer service.",
            ]

            if include_contact:
                prompt_lines.append(f"- Mention customer service email exactly: {email_service}")
            else:
                prompt_lines.append("- Do not mention any email.")

            prompt_lines += ["", "Response:"]

        prompt = "\n".join(prompt_lines)

        # Génération
        inputs = self.response_tokenizer(prompt, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        outputs = self.response_model.generate(  # type: ignore[operator]
            **inputs,
            max_new_tokens=max_length,
            temperature=0.3,
            top_p=0.9,
            do_sample=True,
            repetition_penalty=1.1,
            pad_token_id=getattr(self.response_tokenizer, "eos_token_id", None),
            eos_token_id=getattr(self.response_tokenizer, "eos_token_id", None),
        )

        raw = self.response_tokenizer.decode(outputs[0], skip_special_tokens=True).strip()

        # Extraction réponse
        if lang == "fr":
            response = raw.split("Réponse:", 1)[-1].strip() if "Réponse:" in raw else raw
        else:
            response = raw.split("Response:", 1)[-1].strip() if "Response:" in raw else raw
        
        response = response.strip().strip('"').strip("'")
        response = " ".join(line.strip() for line in response.splitlines() if line.strip()).strip()

        # Détection salutation seule (bilingue)
        def _looks_like_only_salutation(text: str, language: str) -> bool:
            t = text.strip()
            if len(t) >= 60:
                return False
            if language == "fr":
                return bool(re.match(r"^(Monsieur|Madame|Bonjour|Bonsoir)\b", t, flags=re.IGNORECASE))
            else:
                return bool(re.match(r"^(Dear|Hello|Hi|Sir|Madam)\b", t, flags=re.IGNORECASE))

        # Retry si réponse trop courte sur sentiment négatif
        if sentiment == "negative" and (len(response) < 80 or _looks_like_only_salutation(response, lang)):
            if lang == "fr":
                prompt_retry = (
                    prompt
                    + "\n\nIMPORTANT: Répondez en 3 à 5 phrases complètes. "
                    "Incluez des excuses, une solution proposée, et le contact SAV si demandé. "
                    "Ne répondez pas avec une simple formule de politesse."
                )
            else:
                prompt_retry = (
                    prompt
                    + "\n\nIMPORTANT: Respond with 3 to 5 complete sentences. "
                    "Include an apology, a proposed solution, and customer service contact if requested. "
                    "Do not respond with only a greeting."
                )
            
            inputs = self.response_tokenizer(prompt_retry, return_tensors="pt")
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            outputs = self.response_model.generate(  # type: ignore[operator]
                **inputs,
                max_new_tokens=max_length,
                temperature=0.2,
                top_p=0.95,
                do_sample=True,
                repetition_penalty=1.15,
                pad_token_id=getattr(self.response_tokenizer, "eos_token_id", None),
                eos_token_id=getattr(self.response_tokenizer, "eos_token_id", None),
            )
            raw = self.response_tokenizer.decode(outputs[0], skip_special_tokens=True).strip()
            
            if lang == "fr":
                response = raw.split("Réponse:", 1)[-1].strip() if "Réponse:" in raw else raw
            else:
                response = raw.split("Response:", 1)[-1].strip() if "Response:" in raw else raw
            
            response = response.strip().strip('"').strip("'")
            response = " ".join(line.strip() for line in response.splitlines() if line.strip()).strip()

        # Protection email
        response = response.replace(email_service, "___EMAIL_SERVICE___")
        response = re.sub(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "", response)
        response = response.replace("___EMAIL_SERVICE___", email_service)

        # Limite phrases
        response = limit_sentences(response, max_sentences=5)
        return response.strip()

    def generate_all_responses(self, df: pd.DataFrame) -> pd.DataFrame:
        print("=" * 70)
        print("ÉTAPE 2: GÉNÉRATION DES RÉPONSES")
        print("=" * 70 + "\n")

        df = df.copy()
        responses: List[str] = []

        total = len(df)
        print(f"Génération de {total} réponses...\n")

        for idx in range(len(df)):
            row_dict = {str(k): v for k, v in df.iloc[idx].to_dict().items()}
            nom_client = str(row_dict.get('Nom', 'Client'))[:20]
            sentiment_avis = str(row_dict.get('sentiment', 'neutral'))
            
            print(f"  [{idx + 1}/{total}] {nom_client}... ({sentiment_avis})")
            responses.append(self.generate_response(row_dict))

            if (idx + 1) % 10 == 0:
                print(f"  {idx + 1} réponses générées\n")

        df["reponse_generee"] = responses
        print(f"\nGénération terminée: {total} réponses\n")
        return df


_PIPELINE_CACHE: Dict[Tuple[str, str, bool], ReviewAnalysisAndResponsePipeline] = {}
_PIPELINE_LOCK = threading.Lock()


def get_cached_pipeline(
    use_gpu: bool = True,
    sentiment_model: str = "nlptown/bert-base-multilingual-uncased-sentiment",
    response_model: str = "mistralai/Mistral-7B-Instruct-v0.2",
) -> ReviewAnalysisAndResponsePipeline:
    """
    Retourne une instance cache du pipeline (modèles chargés une seule fois).
    Clé du cache: (sentiment_model, response_model, use_gpu)
    """
    key = (sentiment_model, response_model, use_gpu)
    with _PIPELINE_LOCK:
        if key in _PIPELINE_CACHE:
            return _PIPELINE_CACHE[key]
        pipeline = ReviewAnalysisAndResponsePipeline(
            sentiment_model=sentiment_model,
            response_model=response_model,
            use_gpu=use_gpu,
        )
        _PIPELINE_CACHE[key] = pipeline
        return pipeline


def generate_reply_for_single_review(
    product_title: str,
    brand: str,
    avis: Dict[str, Any],
    use_gpu: bool = True,
    sentiment_model: str = "nlptown/bert-base-multilingual-uncased-sentiment",
    response_model: str = "mistralai/Mistral-7B-Instruct-v0.2",
) -> Dict[str, Any]:
    """
    Répondre à UN seul avis (réponse immédiate), en réutilisant le cache modèles.
    """
    pipeline = get_cached_pipeline(
        use_gpu=use_gpu,
        sentiment_model=sentiment_model,
        response_model=response_model,
    )

    sentiment_result = pipeline.analyze_sentiment(avis.get("contenu", ""))

    row: Dict[str, Any] = {
        "Nom": avis.get("profil", ""),
        "Titre de l'avis": avis.get("titre_review", ""),
        "Avis": avis.get("contenu", ""),
        "produit_titre_complet": product_title,
        "brand": brand,
        "sentiment": sentiment_result["sentiment"],
        "etoiles_valeur": avis.get("etoiles_valeur"),
    }

    reply = pipeline.generate_response(row)

    return {
        "sentiment": sentiment_result["sentiment"],
        "reply": reply,
    }