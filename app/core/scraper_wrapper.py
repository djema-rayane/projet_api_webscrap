from app.core.task_manager import task_manager
from app.config import settings
import json
import os

def execute_scraping_task(task_id: str, request_data: dict):
    try:
        # Import ici pour éviter les problèmes de dépendances circulaires
        from scraper import AmazonReviewScraper
        
        task_manager.update_status(task_id, "running")
        
        scraper = AmazonReviewScraper(
            profile_dir=settings.selenium_profile_dir,
            headless=request_data.get("headless", True),
            wait_seconds=settings.default_wait_seconds
        )
        
        def update_progress(message: str):
            task_manager.update_progress(task_id, message)
        
        scraper.set_progress_callback(update_progress)
        
        result = scraper.scrape_multiple_products(
            query=request_data["query"],
            nb_products=request_data["nb_products"],
            france_only=request_data.get("france_only", True),
            limit_per_product=request_data.get("limit_per_product")
        )
        
        output_file = os.path.join(settings.results_dir, f"amazon_reviews_{task_id}.json")
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        task_manager.update_status(task_id, "completed")
        summary = f"Terminé: {result['nb_produits_scrapes']} produits, {result['total_avis_extraits']} avis"
        task_manager.set_result(task_id, output_file, summary)
        
    except Exception as e:
        task_manager.update_status(task_id, "failed")
        task_manager.set_error(task_id, str(e))