from app.core.task_manager import task_manager
from app.config import settings
import json
import os
from pathlib import Path


def execute_scraping_task(task_id: str, request_data: dict):
    scraper = None
    try:
        # Import ici pour éviter les problèmes de dépendances circulaires
        from scraper import AmazonReviewScraper

        task_manager.update_status(task_id, "running")

        # Récupérer le mode de scraping
        mode = request_data.get("mode", "search")

        # Paramètres communs
        headless = request_data.get("headless", True)
        cookies_only = request_data.get("cookies_only", False)

        use_profile = (mode == "search")

        results_dir = Path(settings.results_dir).resolve()
        results_dir.mkdir(parents=True, exist_ok=True)

        cookies_path = str(results_dir / "amazon_session_cookies.pkl")

        task_manager.update_progress(
            task_id,
            f"DEBUG results_dir={results_dir} | cookies_path={cookies_path}"
        )

        if use_profile:
            scraper = AmazonReviewScraper(
                profile_dir=settings.selenium_profile_dir,
                headless=headless,
                wait_seconds=settings.default_wait_seconds,
                cookies_file=cookies_path,
            )
        else:
            scraper = AmazonReviewScraper(
                headless=headless,
                wait_seconds=settings.default_wait_seconds,
                cookies_file=cookies_path,
            )

        def update_progress(message: str):
            task_manager.update_progress(task_id, message)

        scraper.set_progress_callback(update_progress)

        
        if mode == "url":
            # MODE URL: scrape un seul produit (non authentifié)
            result = scraper.scrape_single_product_by_url(
                product_url=request_data["product_url"],
                france_only=request_data.get("france_only", True),
                limit=request_data.get("limit_per_product"),
            )

        elif mode == "url_auth":
            # MODE URL_AUTH: cookies -> (fallback login si autorisé) -> scraping

            product_url = request_data["product_url"]
            france_only = request_data.get("france_only", True)
            limit = request_data.get("limit_per_product") or 30

            username = request_data.get("username")
            password = request_data.get("password")

            
            # - si cookies_only=False => username/password requis (fallback possible)
            # - si cookies_only=True  => pas besoin de creds
            if not cookies_only and (not username or not password):
                raise Exception(
                    "Mode url_auth: username/password manquants. "
                    "Fournis-les OU mets cookies_only=true."
                )

            # - charge cookies -> refresh -> is_logged_in
            # - si KO et cookies_only=False -> login manuel -> save cookies
            result = scraper.scrape_product_reviews_auth(
                product_url=product_url,
                username=username,
                password=password,
                limit=limit,
                france_only=france_only,
                cookies_only=cookies_only,
            )

            if result is None:
                raise Exception(
                    "Scraping url_auth: échec. "
                    "Si cookies_only=true, tes cookies sont probablement invalides/expirés. "
                    "Réessaie avec cookies_only=false + username/password."
                )

        else:
            # MODE SEARCH: scrape plusieurs produits
            result = scraper.scrape_multiple_products(
                query=request_data["query"],
                nb_products=request_data["nb_products"],
                france_only=request_data.get("france_only", True),
                limit_per_product=request_data.get("limit_per_product"),
            )

        # =========================================================
        # Sauvegarder le résultat (dans results_dir)
        # =========================================================
        output_file = str(results_dir / f"amazon_reviews_{task_id}.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        # Mettre à jour le statut
        task_manager.update_status(task_id, "completed")

        # Résumé selon le mode
        if mode in ("url", "url_auth"):
            summary = f"Terminé: {result.get('nb_avis_extraits', 0)} avis extraits"
        else:
            summary = (
                f"Terminé: {result.get('nb_produits_scrapes', 0)} produits, "
                f"{result.get('total_avis_extraits', 0)} avis"
            )

        task_manager.set_result(task_id, output_file, summary)

    except Exception as e:
        task_manager.update_status(task_id, "failed")
        task_manager.set_error(task_id, str(e))

    finally:
        # Sécurité: fermer le driver si une méthode n'a pas pu le faire
        try:
            if scraper is not None:
                scraper.driver.quit()
        except Exception:
            pass
