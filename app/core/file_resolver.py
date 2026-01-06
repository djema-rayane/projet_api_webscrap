from __future__ import annotations

from pathlib import Path


def resolve_scrape_json_path(results_dir: str, scrape_task_id: str) -> str:
    """
    Retrouve automatiquement le fichier JSON de scraping quel que soit le préfixe:
      - amazon_reviews_<id>.json
      - trustpilot_reviews_<id>.json
      - yelp_reviews_<id>.json

    Priorité:
      amazon > trustpilot > yelp > wildcard
    """
    base = Path(results_dir).resolve()

    patterns = [
        f"amazon_reviews_{scrape_task_id}.json",
        f"trustpilot_reviews_{scrape_task_id}.json",
        f"yelp_reviews_{scrape_task_id}.json",
        f"*reviews_{scrape_task_id}.json",
    ]

    for pattern in patterns:
        matches = list(base.glob(pattern))
        if matches:
            matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return str(matches[0])

    raise FileNotFoundError(
        f"Aucun fichier de scraping trouvé pour scrape_task_id={scrape_task_id} dans {base}"
    )
