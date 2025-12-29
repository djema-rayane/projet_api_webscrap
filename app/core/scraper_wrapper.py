from app.core.task_manager import task_manager
from app.config import settings
import json
import os

def execute_scraping_task(task_id: str, request_data: dict):
    try:
        # Import ici pour éviter les problèmes de dépendances circulaires
        from scraper import AmazonReviewScraper
        
        task_manager.update_status(task_id, "running")
        
        # Récupérer le mode de scraping
        mode = request_data.get("mode", "search")
        
        # CORRECTION: Ne pas utiliser de profil en mode URL (session temporaire)
        use_profile = (mode == "search")
        
        if use_profile:
            scraper = AmazonReviewScraper(
                profile_dir=settings.selenium_profile_dir,
                headless=request_data.get("headless", True),
                wait_seconds=settings.default_wait_seconds
            )
        else:
            # Mode URL: pas de profil (évite les conflits de session)
            scraper = AmazonReviewScraper(
                headless=request_data.get("headless", True),
                wait_seconds=settings.default_wait_seconds
            )
        
        def update_progress(message: str):
            task_manager.update_progress(task_id, message)
        
        scraper.set_progress_callback(update_progress)
        
        # Exécuter le scraping selon le mode
        if mode == "url":
            # MODE URL: scrape un seul produit
            result = scraper.scrape_single_product_by_url(
                product_url=request_data["product_url"],
                france_only=request_data.get("france_only", True),
                limit=request_data.get("limit_per_product")
            )
        else:
            # MODE SEARCH: scrape plusieurs produits
            result = scraper.scrape_multiple_products(
                query=request_data["query"],
                nb_products=request_data["nb_products"],
                france_only=request_data.get("france_only", True),
                limit_per_product=request_data.get("limit_per_product")
            )
        
        # Sauvegarder le résultat
        output_file = os.path.join(settings.results_dir, f"amazon_reviews_{task_id}.json")
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        # Mettre à jour le statut
        task_manager.update_status(task_id, "completed")
        
        # Résumé selon le mode
        if mode == "url":
            summary = f"Terminé: {result['nb_avis_extraits']} avis extraits"
        else:
            summary = f"Terminé: {result['nb_produits_scrapes']} produits, {result['total_avis_extraits']} avis"
        
        task_manager.set_result(task_id, output_file, summary)
        
    except Exception as e:
        task_manager.update_status(task_id, "failed")
        task_manager.set_error(task_id, str(e))