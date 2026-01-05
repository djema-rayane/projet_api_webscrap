import csv
import json
import re
import threading
from typing import Dict, Tuple

import pandas as pd
import torch
from transformers import AutoModelForCausalLM, AutoModelForSequenceClassification, AutoTokenizer


def _sanitize_for_csv(value):
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


class ReviewAnalysisAndResponsePipeline:
    """
    Pipeline complet: analyse de sentiment + génération de réponses automatiques
    """

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
        self.sentiment_tokenizer = AutoTokenizer.from_pretrained(sentiment_model)
        self.sentiment_model = AutoModelForSequenceClassification.from_pretrained(sentiment_model)
        self.sentiment_model.to(self.device)
        print("Modèle de sentiment chargé\n")

        # 2) Modèle génération
        print(f"Chargement du modèle de génération: {response_model}")
        self.response_tokenizer = AutoTokenizer.from_pretrained(response_model)

        if self.device == "cuda":
            self.response_model = AutoModelForCausalLM.from_pretrained(
                response_model,
                torch_dtype=torch.float16,
                device_map={"": 0},
                low_cpu_mem_usage=True,
            )
            print("Modèle de génération chargé entièrement sur GPU:0")
        else:
            self.response_model = AutoModelForCausalLM.from_pretrained(
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

    def analyze_sentiment(self, text: str) -> dict:
        if not isinstance(text, str) or not text.strip():
            return {"sentiment": "neutral", "confidence": 0.0, "stars_predicted": 3}

        inputs = self.sentiment_tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self.sentiment_model(**inputs)
            probs = torch.softmax(outputs.logits, dim=-1)
            label_id = int(torch.argmax(probs, dim=-1))
            confidence = float(probs[0][label_id])

        stars = label_id + 1
        sentiment = "negative" if stars <= 2 else ("neutral" if stars == 3 else "positive")

        return {
            "sentiment": sentiment,
            "confidence": round(confidence, 3),
            "stars_predicted": stars,
        }

    def load_and_analyze_json(self, json_file: str) -> pd.DataFrame:
        print("=" * 70)
        print("ÉTAPE 1: ANALYSE DES SENTIMENTS")
        print("=" * 70 + "\n")

        print(f"Chargement: {json_file}")

        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        rows = []

        # Format single_product
        if "avis" in data and "produits" not in data:
            print("Format détecté: Single Product\n")
            total_avis = len(data.get("avis", []))
            print(f"Analyse de {total_avis} avis...\n")

            count = 0
            for avis in data.get("avis", []):
                sentiment_result = self.analyze_sentiment(avis.get("contenu", ""))

                rows.append(
                    {
                        "produit_numero": 1,
                        "produit_titre_complet": data.get("titre", "Produit sans titre"),
                        "brand": data.get("marque", "Marque non disponible"),
                        "avis_numero": avis.get("numero", count + 1),
                        "Nom": avis.get("profil", ""),
                        "Titre de l'avis": avis.get("titre_review", ""),
                        "etoiles_valeur": avis.get("etoiles_valeur"),
                        "Date_str": avis.get("date", ""),
                        "Avis": avis.get("contenu", ""),
                        "sentiment": sentiment_result["sentiment"],
                        "platform": "Amazon",
                    }
                )

                count += 1
                if count % 50 == 0 or count == total_avis:
                    print(f"  [{count}/{total_avis}] avis analysés")

        # Format multi-produits
        elif "produits" in data:
            print("Format détecté: Multi-Produits\n")
            total_avis = sum(len(p.get("avis", [])) for p in data.get("produits", []))
            print(f"Analyse de {total_avis} avis...\n")

            count = 0
            for produit in data.get("produits", []):
                for avis in produit.get("avis", []):
                    sentiment_result = self.analyze_sentiment(avis.get("contenu", ""))

                    rows.append(
                        {
                            "produit_numero": produit.get("produit_numero", 0),
                            "produit_titre_complet": produit.get("titre", ""),
                            "brand": produit.get("marque", "Marque non disponible"),
                            "avis_numero": avis.get("numero", 0),
                            "Nom": avis.get("profil", ""),
                            "Titre de l'avis": avis.get("titre_review", ""),
                            "etoiles_valeur": avis.get("etoiles_valeur"),
                            "Date_str": avis.get("date", ""),
                            "Avis": avis.get("contenu", ""),
                            "sentiment": sentiment_result["sentiment"],
                            "platform": "Amazon",
                        }
                    )

                    count += 1
                    if count % 50 == 0 or count == total_avis:
                        print(f"  [{count}/{total_avis}] avis analysés")

        else:
            print("Format JSON non reconnu!")
            print(f"Clés disponibles: {list(data.keys())}")

        print(f"\nAnalyse terminée: {len(rows)} avis\n")
        return pd.DataFrame(rows)

    def generate_response(self, row: dict, max_length: int = 280) -> str:
        """
        Génère une réponse professionnelle (sortie propre, sans recracher le prompt).
        Fix: évite les réponses trop courtes type "Monsieur X," sur sentiments négatifs.
        + Fix: limite par phrases complètes (pas de phrase coupée).
        """
        nom = row.get("Nom", "") or ""
        titre_avis = row.get("Titre de l'avis", "") or ""
        avis = row.get("Avis", "") or ""
        produit = row.get("produit_titre_complet", "") or ""
        marque = row.get("brand", "") or ""
        sentiment = row.get("sentiment", "neutral") or "neutral"
        etoiles = row.get("etoiles_valeur")

        # Utiliser le NOM complet si dispo
        client_name = nom.strip() if nom.strip() else "Madame, Monsieur"

        if marque and marque != "Marque non disponible":
            marque_clean = marque.lower().replace(" ", "").replace("-", "")
            email_service = f"{marque_clean}@serviceclient.fr"
        else:
            email_service = "support@serviceclient.fr"

        include_contact = sentiment != "positive"
        etoiles_text = f" ({etoiles}/5 étoiles)" if etoiles else ""

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
        prompt = "\n".join(prompt_lines)

        inputs = self.response_tokenizer(prompt, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        outputs = self.response_model.generate(
            **inputs,
            max_new_tokens=max_length,
            temperature=0.3,
            top_p=0.9,
            do_sample=True,
            repetition_penalty=1.1,
            pad_token_id=self.response_tokenizer.eos_token_id,
            eos_token_id=self.response_tokenizer.eos_token_id,
        )

        raw = self.response_tokenizer.decode(outputs[0], skip_special_tokens=True).strip()

        # Garder uniquement après "Réponse:"
        response = raw.split("Réponse:", 1)[-1].strip() if "Réponse:" in raw else raw
        response = response.strip().strip('"').strip("'")

        # Normaliser: enlever lignes vides
        response = " ".join(line.strip() for line in response.splitlines() if line.strip()).strip()

        def _looks_like_only_salutation(text: str) -> bool:
            t = text.strip()
            if len(t) >= 60:
                return False
            return bool(re.match(r"^(Monsieur|Madame|Bonjour|Bonsoir)\b", t, flags=re.IGNORECASE))

        # Retry 1 fois si négatif et réponse trop courte / salutation seule
        if sentiment == "negative" and (len(response) < 80 or _looks_like_only_salutation(response)):
            prompt_retry = (
                prompt
                + "\n\nIMPORTANT: Répondez en 3 à 5 phrases complètes. "
                "Incluez des excuses, une solution proposée, et le contact SAV si demandé. "
                "Ne répondez pas avec une simple formule de politesse."
            )
            inputs = self.response_tokenizer(prompt_retry, return_tensors="pt")
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            outputs = self.response_model.generate(
                **inputs,
                max_new_tokens=max_length,
                temperature=0.2,
                top_p=0.95,
                do_sample=True,
                repetition_penalty=1.15,
                pad_token_id=self.response_tokenizer.eos_token_id,
                eos_token_id=self.response_tokenizer.eos_token_id,
            )
            raw = self.response_tokenizer.decode(outputs[0], skip_special_tokens=True).strip()
            response = raw.split("Réponse:", 1)[-1].strip() if "Réponse:" in raw else raw
            response = response.strip().strip('"').strip("'")
            response = " ".join(line.strip() for line in response.splitlines() if line.strip()).strip()

        # Supprimer emails sauf celui du SAV calculé
        response = response.replace(email_service, "___EMAIL_SERVICE___")
        response = re.sub(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "", response)
        response = response.replace("___EMAIL_SERVICE___", email_service)

        # Limiter à 5 phrases complètes (évite phrase coupée + retire les \n)
        response = limit_sentences(response, max_sentences=5)

        return response.strip()

    def generate_all_responses(self, df: pd.DataFrame) -> pd.DataFrame:
        print("=" * 70)
        print("ÉTAPE 2: GÉNÉRATION DES RÉPONSES")
        print("=" * 70 + "\n")

        df = df.copy()
        responses = []

        total = len(df)
        print(f"Génération de {total} réponses...\n")

        for idx, row in df.iterrows():
            print(f"  [{idx+1}/{total}] {str(row.get('Nom', 'Client'))[:20]}... ({row.get('sentiment', 'neutral')})")
            responses.append(self.generate_response(row.to_dict()))

            if (idx + 1) % 10 == 0:
                print(f"  {idx + 1} réponses générées\n")

        df["reponse_generee"] = responses
        print(f"\nGénération terminée: {total} réponses\n")
        return df

    def run_full_pipeline(self, json_file: str, output_csv: str = "reviews_with_responses.csv") -> pd.DataFrame:
        print("\n" + "=" * 70)
        print("PIPELINE COMPLET: ANALYSE + GÉNÉRATION DE RÉPONSES")
        print("=" * 70 + "\n")

        df = self.load_and_analyze_json(json_file)

        if "sentiment" not in df.columns:
            print("ERREUR: La colonne 'sentiment' n'a pas été créée!")
            print(f"Colonnes disponibles: {df.columns.tolist()}")
            return df

        df = self.generate_all_responses(df)

        # Sanitize colonnes texte (évite CSV "multi-lignes")
        for col in [
            "produit_titre_complet",
            "brand",
            "Nom",
            "Titre de l'avis",
            "Avis",
            "reponse_generee",
        ]:
            if col in df.columns:
                df[col] = df[col].map(_sanitize_for_csv)

        df.to_csv(
            output_csv,
            index=False,
            encoding="utf-8",
            sep=",",
            quoting=csv.QUOTE_ALL,
            escapechar="\\",
        )
        print(f"Fichier sauvegardé: {output_csv}")

        return df


# ----------------------------
# Cache global (singleton)
# ----------------------------
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


def process_reviews_from_json(
    json_file: str,
    output_csv: str = "reviews_with_responses.csv",
    use_gpu: bool = True,
    sentiment_model: str = "nlptown/bert-base-multilingual-uncased-sentiment",
    response_model: str = "mistralai/Mistral-7B-Instruct-v0.2",
) -> pd.DataFrame:
    """
    JSON -> sentiment -> réponses -> CSV
    """
    pipeline = get_cached_pipeline(
        use_gpu=use_gpu,
        sentiment_model=sentiment_model,
        response_model=response_model,
    )
    return pipeline.run_full_pipeline(json_file, output_csv)


def generate_reply_for_single_review(
    product_title: str,
    brand: str,
    avis: dict,
    use_gpu: bool = True,
    sentiment_model: str = "nlptown/bert-base-multilingual-uncased-sentiment",
    response_model: str = "mistralai/Mistral-7B-Instruct-v0.2",
) -> dict:
    """
    Répondre à UN seul avis (réponse immédiate), en réutilisant le cache modèles.
    """
    pipeline = get_cached_pipeline(
        use_gpu=use_gpu,
        sentiment_model=sentiment_model,
        response_model=response_model,
    )

    sentiment_result = pipeline.analyze_sentiment(avis.get("contenu", ""))

    row = {
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
