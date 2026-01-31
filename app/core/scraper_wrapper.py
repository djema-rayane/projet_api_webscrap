from typing import Optional, Dict, Any
from app.core.task_manager import task_manager
from app.config import settings
from pathlib import Path

from app.database import SessionLocal
from app.crud import (
    creer_session_scraping,
    finaliser_session_scraping,
    creer_produit,
)


def execute_scraping_task(task_id: str, request_data: Dict[str, Any]) -> None:
    """
    Exécute une tâche de scraping avec insertion EN TEMPS RÉEL.
    Le scraper gère l'insertion directe en BDD via set_db_session().
    """
    from app.scrapers.amazon_scraper import AmazonReviewScraper
    
    scraper: Optional[AmazonReviewScraper] = None
    db = None
    session_scraping = None
    
    try:
        # Initialiser la session BDD
        db = SessionLocal()

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

        # Déterminer la source selon le mode
        source_map = {
            "search": "amazon",
            "url": "amazon",
            "url_auth": "amazon",
            "trustpilot": "trustpilot",
            "yelp": "yelp",
        }
        source = source_map.get(mode, "amazon")

        # Créer la session de scraping dans la BDD avec task_id
        session_scraping = creer_session_scraping(
            db=db,
            task_id=task_id,
            type_scraping=mode,
            source=source,
            query=request_data.get("query") if mode == "search" else None,
            filtre_france=request_data.get("france_only", True),
            nb_avis_demandes=request_data.get("limit_per_product"),
        )
        
        task_manager.update_progress(
            task_id,
            f"Session BDD créée : task_id={task_id}, db_id={session_scraping.id}"
        )

        # =====================================================
        # Amazon scraper init avec BDD
        # =====================================================
        if mode in ("search", "url", "url_auth"):
            scraper = AmazonReviewScraper(
                profile_dir=settings.selenium_profile_dir if use_profile else None,
                headless=headless,
                wait_seconds=settings.default_wait_seconds,
                cookies_file=str(cookies_path),
                db_session=db,
            )

            scraper.set_progress_callback(
                lambda msg: task_manager.update_progress(task_id, msg)
            )
            
            # Configurer la session BDD dans le scraper
            scraper.set_db_session(db, session_scraping)

        # =====================================================
        # Dispatch by mode
        # =====================================================
        if mode == "url":
            assert scraper is not None, "Scraper non initialisé pour mode 'url'"
            
            product_url = request_data["product_url"]
            france_only = request_data.get("france_only", True)
            limit = request_data.get("limit_per_product")
            
            scraper.driver.get(product_url)
            scraper.accept_cookies_if_present()
            
            product_title = scraper.extract_product_title()
            brand = scraper.extract_brand()
            
            # Créer le produit et l'assigner au scraper
            scraper.produit_actuel = creer_produit(
                db=db,
                session_id=int(session_scraping.id),  # Cast explicite
                source=source,
                titre=product_title,
                url=product_url,
                marque=brand,
            )
            
            task_manager.update_progress(
                task_id,
                f"Produit : {product_title[:50]}..."
            )
            
            # Scroll
            for i in range(3):
                scroll_position = (i + 1) * (scraper.driver.execute_script("return document.body.scrollHeight") // 3)
                scraper.driver.execute_script(f"window.scrollTo(0, {scroll_position});")
                import time
                time.sleep(1)
            
            # L'insertion se fait automatiquement dans extract_reviews
            scraper.extract_reviews(france_only=france_only, limit=limit, insert_db=True)

        elif mode == "url_auth":
            assert scraper is not None, "Scraper non initialisé pour mode 'url_auth'"
            
            product_url = request_data["product_url"]
            username = request_data.get("username")
            password = request_data.get("password")
            limit = request_data.get("limit_per_product", 30)
            france_only = request_data.get("france_only", True)
            
            # Login
            if not scraper.ensure_logged_in(username=username, password=password, cookies_only=cookies_only):
                raise Exception("Échec authentification")
            
            # Accès produit
            scraper.driver.get(product_url)
            import time
            time.sleep(3)
            scraper.accept_cookies_if_present()
            
            product_title = scraper.extract_product_title()
            brand = scraper.extract_brand()
            
            # Créer le produit et l'assigner au scraper
            scraper.produit_actuel = creer_produit(
                db=db,
                session_id=int(session_scraping.id),  # Cast explicite
                source=source,
                titre=product_title,
                url=product_url,
                marque=brand,
            )
            
            task_manager.update_progress(
                task_id,
                f"Produit : {product_title[:50]}..."
            )
            
            # Aller sur la page complète des avis
            if not scraper.click_voir_plus_commentaires():
                task_manager.update_progress(task_id, "Impossible d'accéder à la page des avis")
            else:
                scraper.click_traduire_commentaires()
                
                # Pagination avec insertion auto
                page = 1
                max_pages = 50
                
                while scraper.avis_count < limit and page <= max_pages:
                    task_manager.update_progress(
                        task_id,
                        f"Page {page} - {scraper.avis_count} avis insérés"
                    )
                    
                    # L'insertion se fait automatiquement
                    page_reviews = scraper.extract_reviews_from_page_auth(
                        france_only=france_only,
                        insert_db=True
                    )
                    
                    if not page_reviews:
                        break
                    
                    if scraper.avis_count >= limit:
                        break
                    
                    if not scraper.click_next_page_reviews_auth():
                        break
                    
                    page += 1

        elif mode == "trustpilot":
            from app.scrapers.trustpilot_scraper import scrape_trustpilot_json
            
            result = scrape_trustpilot_json(
                domain=request_data["trustpilot_domain"],
                lang=request_data.get("trustpilot_lang", "fr"),
                max_pages=request_data.get("max_pages"),
                limit=request_data.get("limit_per_product") or 200,
            )
            
            _insert_single_product_to_db(db, int(session_scraping.id), source, result)

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
            
            _insert_single_product_to_db(db, int(session_scraping.id), source, result)

        else:  # mode == "search"
            assert scraper is not None, "Scraper non initialisé pour mode 'search'"
            
            result = scraper.scrape_multiple_products(
                query=request_data["query"],
                nb_products=request_data["nb_products"],
                france_only=request_data.get("france_only", True),
                limit_per_product=request_data.get("limit_per_product"),
            )
            
            _insert_multiple_products_to_db(db, int(session_scraping.id), source, result)

        # =====================================================
        # Finaliser la session dans la BDD (via task_id)
        # =====================================================
        nb_produits = 1 if mode in ("url", "url_auth", "trustpilot", "yelp") else request_data.get("nb_products", 1)
        
        # Utiliser scraper.avis_count pour les modes Amazon
        avis_count = scraper.avis_count if scraper else 0
        
        finaliser_session_scraping(
            db=db,
            session_id=int(session_scraping.id), 
            nb_avis_extraits=avis_count,
            nb_produits_scrapes=nb_produits,
            statut="completed",
        )
        
        task_manager.update_status(task_id, "completed")
        
        summary = f"Terminé : {avis_count} avis insérés en temps réel"
        task_manager.set_result(
            task_id, 
            f"BDD - task_id: {task_id}",  
            summary
        )
        task_manager.update_progress(task_id, summary)

    except Exception as e:
        if session_scraping and db:
            avis_count = scraper.avis_count if scraper else 0
            finaliser_session_scraping(
                db=db,
                session_id=int(session_scraping.id),
                nb_avis_extraits=avis_count,
                statut="failed",
                erreur=str(e),
            )
        
        task_manager.update_status(task_id, "failed")
        task_manager.set_error(task_id, str(e))

    finally:
        if scraper:
            try:
                scraper.driver.quit()
            except Exception:
                pass
        
        if db:
            db.close()


# =====================================================
# Fonctions helper (pour Trustpilot/Yelp/Search)
# =====================================================

def _insert_single_product_to_db(db, session_id: int, source: str, result: Dict[str, Any]) -> None:
    """Insère un produit unique et ses avis dans la BDD."""
    from app.crud import creer_produit, inserer_avis_batch
    
    produit = creer_produit(
        db=db,
        session_id=session_id,
        source=source,
        titre=result.get("titre", "Produit sans titre"),
        url=result.get("url", ""),
        marque=result.get("marque"),
    )
    
    avis_liste = result.get("avis", [])
    if avis_liste:
        inserer_avis_batch(
            db=db,
            session_id=session_id,  # Déjà un int
            produit_id=int(produit.id),
            source=source,
            avis_liste=avis_liste,
        )


def _insert_multiple_products_to_db(db, session_id: int, source: str, result: Dict[str, Any]) -> None:
    """Insère plusieurs produits et leurs avis dans la BDD."""
    from app.crud import creer_produit, inserer_avis_batch
    
    produits_data = result.get("produits", [])
    
    for produit_data in produits_data:
        produit = creer_produit(
            db=db,
            session_id=session_id,
            source=source,
            titre=produit_data.get("titre", ""),
            url=produit_data.get("url", ""),
            marque=produit_data.get("marque"),
            produit_numero=produit_data.get("produit_numero"),
        )
        
        avis_liste = produit_data.get("avis", [])
        if avis_liste:
            inserer_avis_batch(
                db=db,
                session_id=session_id,  # Déjà un int
                produit_id=int(produit.id),
                source=source,
                avis_liste=avis_liste,
            )