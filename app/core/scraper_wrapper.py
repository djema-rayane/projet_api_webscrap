from app.core.task_manager import task_manager
from app.config import settings
import json
from pathlib import Path
from datetime import datetime


def execute_scraping_task(task_id: str, request_data: dict):
    scraper = None
    try:
        from app.scrapers.amazon_scraper import AmazonReviewScraper

        task_manager.update_status(task_id, "running")

        mode = request_data.get("mode", "search")
        headless = request_data.get("headless", True)
        cookies_only = request_data.get("cookies_only", False)

        use_profile = (mode == "search")

        # =====================================================
        # Results / Cookies paths
        # =====================================================
        results_dir = Path(settings.results_dir).resolve()
        results_dir.mkdir(parents=True, exist_ok=True)

        cookies_path = results_dir / "amazon_session_cookies.pkl"

        task_manager.update_progress(
            task_id,
            f"results_dir={results_dir} | cookies_path={cookies_path}"
        )

        # =====================================================
        # Amazon scraper init (only if needed)
        # =====================================================
        if mode in ("search", "url", "url_auth"):
            scraper = AmazonReviewScraper(
                profile_dir=settings.selenium_profile_dir if use_profile else None,
                headless=headless,
                wait_seconds=settings.default_wait_seconds,
                cookies_file=str(cookies_path),
            )

            scraper.set_progress_callback(
                lambda msg: task_manager.update_progress(task_id, msg)
            )

        # =====================================================
        # Dispatch by mode
        # =====================================================
        if mode == "url":
            result = scraper.scrape_single_product_by_url(
                product_url=request_data["product_url"],
                france_only=request_data.get("france_only", True),
                limit=request_data.get("limit_per_product"),
            )

        elif mode == "url_auth":
            result = scraper.scrape_product_reviews_auth(
                product_url=request_data["product_url"],
                username=request_data.get("username"),
                password=request_data.get("password"),
                limit=request_data.get("limit_per_product") or 30,
                france_only=request_data.get("france_only", True),
                cookies_only=cookies_only,
            )

            if result is None:
                raise Exception("Échec URL_AUTH (cookies invalides ?)")

        elif mode == "trustpilot":
            from app.scrapers.trustpilot_scraper import scrape_trustpilot_json

            result = scrape_trustpilot_json(
                domain=request_data["trustpilot_domain"],
                lang=request_data.get("trustpilot_lang", "fr"),
                max_pages=request_data.get("max_pages"),
                limit=request_data.get("limit_per_product") or 200,
            )

        elif mode == "yelp":
            from app.scrapers.yelp_scraper import scrape_yelp_json

            result = scrape_yelp_json(
                business_url=request_data["yelp_business_url"],
                max_pages=request_data.get("max_pages", 1),
                limit=request_data.get("limit_per_product") or 200,
                headless=headless,
                task_id=task_id,
                results_dir=settings.results_dir,
            )


        else:
            result = scraper.scrape_multiple_products(
                query=request_data["query"],
                nb_products=request_data["nb_products"],
                france_only=request_data.get("france_only", True),
                limit_per_product=request_data.get("limit_per_product"),
            )

        # =====================================================
        # Save JSON
        # =====================================================
        prefix_map = {
            "search": "amazon",
            "url": "amazon",
            "url_auth": "amazon",
            "trustpilot": "trustpilot",
            "yelp": "yelp",
        }

        prefix = prefix_map.get(mode, "scrape")
        output_file = results_dir / f"{prefix}_reviews_{task_id}.json"

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        task_manager.update_status(task_id, "completed")

        # =====================================================
        # Summary
        # =====================================================
        if mode in ("url", "url_auth", "trustpilot", "yelp"):
            summary = f"Terminé: {result.get('nb_avis_extraits', 0)} avis extraits"
        else:
            summary = (
                f"Terminé: {result.get('nb_produits_scrapes', 0)} produits, "
                f"{result.get('total_avis_extraits', 0)} avis"
            )

        task_manager.set_result(task_id, str(output_file), summary)

    except Exception as e:
        task_manager.update_status(task_id, "failed")
        task_manager.set_error(task_id, str(e))

    finally:
        if scraper:
            try:
                scraper.driver.quit()
            except Exception:
                pass
