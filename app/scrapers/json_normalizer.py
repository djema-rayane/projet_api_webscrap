from datetime import datetime
from typing import Any, Optional


def normalize_review(
    *,
    numero: int,
    profil: str = "",
    titre_review: str = "",
    contenu: str = "",
    date: str = "",
    etoiles: Optional[str] = None,
    etoiles_valeur: Optional[float] = None,
) -> dict[str, Any]:
    return {
        "numero": numero,
        "profil": profil or "",
        "titre_review": titre_review or "",
        "etoiles": etoiles,
        "etoiles_valeur": etoiles_valeur,
        "date": date or "",
        "contenu": contenu or "",
    }


def build_result_json(
    *,
    source: str,
    url: str,
    titre: str,
    marque: str = "",
    filtre_france: bool = False,
    limite_demandee: int = 0,
    nb_pages_scrapees: int = 0,
    avis: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "type": "authenticated_scraping",  # on garde ton type existant pour compat modèle
        "source": source,
        "titre": titre,
        "marque": marque,
        "url": url,
        "date_extraction": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "filtre_france": filtre_france,
        "limite_demandee": limite_demandee,
        "nb_avis_extraits": len(avis),
        "nb_pages_scrapees": nb_pages_scrapees,
        "avis": avis,
    }
