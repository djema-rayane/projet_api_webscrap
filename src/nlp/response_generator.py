# src/nlp/response_generator.py

from typing import Literal

Tone = Literal["formel", "amical", "empathique"]


def _normalize_lang(lang: str) -> str:
    """Simplifie le code langue (fr-FR -> fr, en-US -> en, etc.)."""
    if not lang:
        return "fr"
    lang = lang.lower()
    if lang.startswith("fr"):
        return "fr"
    if lang.startswith("en"):
        return "en"
    return "fr"


def generate_reply(
    avis: str,
    sentiment: str,
    langue: str,
    platform: str | None,
    brand: str | None,
    tone: Tone = "formel",
) -> str:
    """
    Génère une réponse en fonction :
    - avis : texte de l'avis
    - sentiment : positive / negative / neutral
    - langue : fr / en
    - platform : Yelp, Trustpilot, ...
    - brand : Carhartt WIP, Le Petit Cler, ...
    - tone : formel / amical / empathique
    """

    langue = _normalize_lang(langue)
    sentiment = sentiment.lower()
    tone = tone.lower()

    platform = platform or ""
    brand = brand or "notre enseigne"

    # ======================= FRANÇAIS =======================
    if langue == "fr":
        # Ouverture / fermeture selon le ton
        if tone == "amical":
            opening = "Bonjour 😊"
            closing = "\n\nÀ bientôt,\nL'équipe Service Client"
        elif tone == "empathique":
            opening = "Bonjour 🙏"
            closing = "\n\nCordialement,\nL'équipe Service Client"
        else:  # formel
            opening = "Bonjour,"
            closing = "\n\nCordialement,\nL'équipe Service Client"

        if sentiment == "positive":
            if tone == "formel":
                core = (
                    f"Merci pour votre avis positif sur {brand} et pour votre confiance.\n"
                    f"Nous sommes ravis de voir que votre expérience sur {platform} s'est bien passée."
                )
            elif tone == "amical":
                core = (
                    f"Un grand merci pour votre super retour sur {brand} 🥰\n"
                    f"Ça nous fait vraiment plaisir de savoir que votre expérience s'est bien passée via {platform}."
                )
            else:  # empathique
                core = (
                    f"Merci du fond du cœur pour votre message sur {brand} ❤️\n"
                    f"Nous sommes très heureux d'avoir pu vous offrir une belle expérience, "
                    f"et votre retour sur {platform} compte beaucoup pour nous."
                )

        elif sentiment == "negative":
            if tone == "formel":
                core = (
                    f"Nous sommes désolés d'apprendre que votre expérience avec {brand} via {platform} "
                    "n’a pas été à la hauteur de vos attentes.\n"
                    "Merci d'avoir pris le temps de nous faire part de ces éléments ; "
                    "nous allons analyser la situation afin de nous améliorer."
                )
            elif tone == "amical":
                core = (
                    f"Merci d'avoir pris le temps de nous laisser un avis sur {brand}, même si l'expérience "
                    "n'était pas au rendez-vous 😔\n"
                    "On aimerait vraiment comprendre ce qui s'est passé pour pouvoir améliorer les choses."
                )
            else:  # empathique
                core = (
                    f"Nous sommes vraiment navrés de lire que votre expérience avec {brand} via {platform} "
                    "ne s'est pas bien déroulée 😔\n"
                    "Votre ressenti est important pour nous et nous vous remercions sincèrement de l'avoir partagé.\n"
                    "Si vous le souhaitez, vous pouvez nous contacter directement afin que nous trouvions une solution "
                    "ensemble."
                )

        else:  # neutral
            if tone == "formel":
                core = (
                    f"Merci pour votre retour au sujet de {brand}.\n"
                    "Vos remarques nous aident à mieux comprendre vos attentes et à faire évoluer notre service."
                )
            elif tone == "amical":
                core = (
                    f"Merci pour votre avis sur {brand} 😊\n"
                    "On note vos retours et on va faire en sorte de continuer à s'améliorer."
                )
            else:  # empathique
                core = (
                    f"Merci d'avoir partagé votre expérience avec {brand}.\n"
                    "Nous prenons vos remarques avec beaucoup d'attention afin d'améliorer nos services."
                )

        return f"{opening}\n\n{core}{closing}"

    # ======================= ANGLAIS =======================
    else:
        if tone == "amical":
            opening = "Hi there 😊"
            closing = "\n\nBest regards,\nThe Customer Service Team"
        elif tone == "empathique":
            opening = "Hello 🙏"
            closing = "\n\nBest regards,\nThe Customer Service Team"
        else:
            opening = "Hello,"
            closing = "\n\nBest regards,\nThe Customer Service Team"

        if sentiment == "positive":
            if tone == "formel":
                core = (
                    f"Thank you for your positive feedback about {brand}.\n"
                    f"We're glad to hear your experience on {platform} went well."
                )
            elif tone == "amical":
                core = (
                    f"Thank you so much for the great review about {brand} 🥰\n"
                    f"We're really happy that you enjoyed your experience via {platform}."
                )
            else:
                core = (
                    f"Thank you from the bottom of our hearts for your kind words about {brand} ❤️\n"
                    f"Knowing that your experience via {platform} went well truly means a lot to us."
                )

        elif sentiment == "negative":
            if tone == "formel":
                core = (
                    f"We're sorry to hear that your experience with {brand} through {platform} "
                    "did not meet your expectations.\n"
                    "Thank you for taking the time to share this with us; we will review the situation carefully."
                )
            elif tone == "amical":
                core = (
                    f"Thanks for sharing your feedback about {brand}, even though things didn't go as expected 😔\n"
                    "We’d really like to understand what happened so we can improve."
                )
            else:
                core = (
                    f"We're truly sorry to read that your experience with {brand} via {platform} "
                    "was disappointing 😔\n"
                    "Your feelings matter to us, and we really appreciate you taking the time to explain the situation.\n"
                    "If you’d like, feel free to contact us directly so we can try to sort this out together."
                )

        else:  # neutral
            if tone == "formel":
                core = (
                    f"Thank you for your feedback about {brand}.\n"
                    "Your comments help us better understand your expectations and improve our service."
                )
            elif tone == "amical":
                core = (
                    f"Thanks for your review about {brand} 😊\n"
                    "We appreciate your feedback and will use it to keep improving."
                )
            else:
                core = (
                    f"Thank you for taking the time to share your experience with {brand}.\n"
                    "We carefully consider this type of feedback to improve our services."
                )

        return f"{opening}\n\n{core}{closing}"
