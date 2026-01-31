from typing import Optional, List
from pathlib import Path
import csv
import json
from datetime import datetime

from app.core.analysis_task_manager import analysis_task_manager
from app.database import SessionLocal, Avis, SessionScraping
from app.crud import (
    get_session_by_task_id,
    get_avis_non_analyses_by_task_id,
    get_avis_sans_reponse_by_task_id,
    recuperer_avis_non_analyses,
    recuperer_avis_sans_reponse,
    mettre_a_jour_sentiment,
    mettre_a_jour_reponse,
)


# ============================================================================
# FONCTION 1 : ANALYSE DE SENTIMENT UNIQUEMENT
# ============================================================================

def execute_sentiment_analysis_task(
    analysis_task_id: str,
    scrape_task_id: Optional[str],
    use_gpu: bool,
) -> None:
    """
    Exécute UNIQUEMENT l'analyse de sentiment (pas de génération de réponses).
    Remplit les colonnes : sentiment, score_sentiment, date_analyse, statut='analyzed'
    """
    print("\n" + "=" * 80)
    print("ANALYSE DE SENTIMENT UNIQUEMENT")
    print("=" * 80)
    print(f"analysis_task_id: {analysis_task_id}")
    print(f"scrape_task_id: {scrape_task_id}")
    print(f"use_gpu: {use_gpu}")
    print("=" * 80 + "\n")
    
    db = None
    
    try:
        # Initialiser la session BDD
        print("1. Initialisation de la session BDD...")
        db = SessionLocal()
        print("Session BDD créée\n")
        
        analysis_task_manager.update_status(analysis_task_id, "running")
        
        # Mode ciblé ou global
        if scrape_task_id:
            print(f"2. MODE CIBLÉ : session '{scrape_task_id}'")
            session = get_session_by_task_id(db, scrape_task_id)
            if not session:
                raise ValueError(f"Session '{scrape_task_id}' introuvable")
            
            print(f"Session trouvée : ID={session.id}\n")
            analysis_task_manager.update_progress(
                analysis_task_id,
                f"Mode ciblé : session '{scrape_task_id}'"
            )
            
            avis_a_analyser = get_avis_non_analyses_by_task_id(db, scrape_task_id)
        else:
            print("2. MODE GLOBAL : tous les avis non analysés")
            analysis_task_manager.update_progress(
                analysis_task_id,
                "Mode global : tous les avis non analysés"
            )
            
            avis_a_analyser = recuperer_avis_non_analyses(db, limite=10000)
        
        print(f"{len(avis_a_analyser)} avis à analyser\n")
        
        if not avis_a_analyser:
            print("AUCUN AVIS À ANALYSER")
            analysis_task_manager.update_status(analysis_task_id, "completed")
            analysis_task_manager.update_progress(
                analysis_task_id, "Aucun avis à analyser"
            )
            return
        
        nb_avis = len(avis_a_analyser)
        analysis_task_manager.update_progress(
            analysis_task_id,
            f"{nb_avis} avis à analyser"
        )

        # Charger le pipeline
        print("3. CHARGEMENT DU PIPELINE")
        print("=" * 80)
        
        analysis_task_manager.update_progress(
            analysis_task_id,
            "Chargement du modèle de sentiment…",
        )
        
        from app.core.review_pipeline import get_cached_pipeline
        import torch
        
        print(f"CUDA disponible : {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"GPU détecté : {torch.cuda.get_device_name(0)}")
        
        print("\nChargement du pipeline...")
        pipeline = get_cached_pipeline(use_gpu=use_gpu)
        print("PIPELINE CHARGÉ !\n")
        
        # Analyse de sentiment
        print("4. ANALYSE DE SENTIMENT")
        print("=" * 80)
        
        nb_analyses = 0
        nb_erreurs = 0
        batch_size = 50
        
        for i in range(0, len(avis_a_analyser), batch_size):
            batch = avis_a_analyser[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(avis_a_analyser) + batch_size - 1) // batch_size
            
            print(f"Batch {batch_num}/{total_batches} ({len(batch)} avis)")
            
            for avis in batch:
                try:
                    # Cast explicite pour mypy
                    contenu = str(avis.contenu) if avis.contenu else ""
                    sentiment_result = pipeline.analyze_sentiment(contenu)
                    
                    sentiment_map = {
                        "positive": "positif",
                        "negative": "negatif",
                        "neutral": "neutre",
                    }
                    sentiment_fr = sentiment_map.get(
                        sentiment_result["sentiment"], 
                        sentiment_result["sentiment"]
                    )
                    
                    mettre_a_jour_sentiment(
                        db=db,
                        avis_id=int(avis.id),
                        sentiment=sentiment_fr,
                        score_sentiment=sentiment_result["confidence"],
                    )
                    
                    nb_analyses += 1
                    
                    if nb_analyses <= 5:
                        print(f"   Avis #{nb_analyses}: {sentiment_fr} ({sentiment_result['confidence']:.3f})")
                
                except Exception as e:
                    nb_erreurs += 1
                    print(f"   Erreur avis ID={avis.id}: {e}")
                    continue
            
            print(f"   -> {nb_analyses}/{nb_avis} analysés\n")
            
            analysis_task_manager.update_progress(
                analysis_task_id,
                f"Sentiment analysé : {nb_analyses}/{nb_avis}"
            )
        
        print("=" * 80)
        print("ANALYSE TERMINÉE")
        print(f"   - Réussis : {nb_analyses}/{nb_avis}")
        print(f"   - Erreurs : {nb_erreurs}")
        print("=" * 80 + "\n")
        
        analysis_task_manager.set_result(analysis_task_id, "Sentiments analysés")
        analysis_task_manager.update_status(analysis_task_id, "completed")
        
        target_msg = f"session '{scrape_task_id}'" if scrape_task_id else "tous les avis"
        analysis_task_manager.update_progress(
            analysis_task_id,
            f"Analyse terminée pour {target_msg} : {nb_analyses} sentiments"
        )

    except Exception as e:
        print(f"\nERREUR : {e}")
        analysis_task_manager.update_status(analysis_task_id, "failed")
        analysis_task_manager.set_error(analysis_task_id, str(e))
        import traceback
        traceback.print_exc()
    
    finally:
        if db:
            db.close()


# ============================================================================
# FONCTION 2 : GÉNÉRATION DE RÉPONSES UNIQUEMENT
# ============================================================================

def execute_response_generation_task(
    analysis_task_id: str,
    scrape_task_id: Optional[str],
    use_gpu: bool,
    output_csv: bool,
    output_json: bool,
) -> None:
    """
    Exécute UNIQUEMENT la génération de réponses (pas d'analyse de sentiment).
    Remplit les colonnes : reponse_generee, date_reponse, statut='responded'
    
    PRÉ-REQUIS : Les avis doivent avoir un sentiment analysé (sentiment != NULL)
    """
    print("\n" + "=" * 80)
    print("GÉNÉRATION DE RÉPONSES UNIQUEMENT")
    print("=" * 80)
    print(f"analysis_task_id: {analysis_task_id}")
    print(f"scrape_task_id: {scrape_task_id}")
    print(f"use_gpu: {use_gpu}")
    print(f"output_csv: {output_csv}")
    print(f"output_json: {output_json}")
    print("=" * 80 + "\n")
    
    db = None
    
    try:
        # Initialiser la session BDD
        print("1. Initialisation de la session BDD...")
        db = SessionLocal()
        print("Session BDD créée\n")
        
        analysis_task_manager.update_status(analysis_task_id, "running")
        
        # Mode ciblé ou global
        if scrape_task_id:
            print(f"2. MODE CIBLÉ : session '{scrape_task_id}'")
            session = get_session_by_task_id(db, scrape_task_id)
            if not session:
                raise ValueError(f"Session '{scrape_task_id}' introuvable")
            
            print(f"Session trouvée : ID={session.id}\n")
            analysis_task_manager.update_progress(
                analysis_task_id,
                f"Mode ciblé : session '{scrape_task_id}'"
            )
            
            avis_sans_reponse = get_avis_sans_reponse_by_task_id(db, scrape_task_id)
        else:
            print("2. MODE GLOBAL : tous les avis sans réponse")
            analysis_task_manager.update_progress(
                analysis_task_id,
                "Mode global : tous les avis sans réponse"
            )
            
            avis_sans_reponse = recuperer_avis_sans_reponse(db, limite=10000)
        
        print(f"{len(avis_sans_reponse)} avis sans réponse trouvés\n")
        
        print("3. VALIDATION DES SENTIMENTS")
        print("=" * 80)
        
        avis_sans_sentiment = [a for a in avis_sans_reponse if a.sentiment is None]
        
        if avis_sans_sentiment:
            nb_sans_sentiment = len(avis_sans_sentiment)
            nb_total = len(avis_sans_reponse)
            
            error_msg = (
                f"ERREUR : {nb_sans_sentiment}/{nb_total} avis n'ont pas de sentiment analysé.\n"
                f"   -> Vous devez d'abord exécuter l'analyse de sentiment via POST /analysis/sentiment\n"
                f"   -> IDs concernés : {[a.id for a in avis_sans_sentiment[:5]]}{'...' if nb_sans_sentiment > 5 else ''}"
            )
            
            print(error_msg)
            print("=" * 80 + "\n")
            
            analysis_task_manager.update_status(analysis_task_id, "failed")
            analysis_task_manager.set_error(analysis_task_id, error_msg)
            
            raise ValueError(
                f"Impossible de générer des réponses : {nb_sans_sentiment} avis sans sentiment. "
                f"Exécutez d'abord POST /analysis/sentiment"
            )
        
        print(f"Tous les {len(avis_sans_reponse)} avis ont un sentiment analysé")
        print("=" * 80 + "\n")
        
        if not avis_sans_reponse:
            print("AUCUNE RÉPONSE À GÉNÉRER")
            analysis_task_manager.update_status(analysis_task_id, "completed")
            analysis_task_manager.update_progress(
                analysis_task_id, "Aucune réponse à générer"
            )
            return
        
        nb_reponses_a_generer = len(avis_sans_reponse)
        analysis_task_manager.update_progress(
            analysis_task_id,
            f"{nb_reponses_a_generer} réponses à générer"
        )

        # Charger le pipeline
        print("4. CHARGEMENT DU PIPELINE")
        print("=" * 80)
        
        analysis_task_manager.update_progress(
            analysis_task_id,
            "Chargement du modèle de génération…",
        )
        
        from app.core.review_pipeline import get_cached_pipeline
        import torch
        
        print(f"CUDA disponible : {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"GPU détecté : {torch.cuda.get_device_name(0)}")
        
        print("\nChargement du pipeline...")
        pipeline = get_cached_pipeline(use_gpu=use_gpu)
        print("PIPELINE CHARGÉ !\n")
        
        # Génération de réponses
        print("5. GÉNÉRATION DE RÉPONSES")
        print("=" * 80)
        
        nb_reponses = 0
        nb_erreurs = 0
        batch_size = 10
        
        for i in range(0, len(avis_sans_reponse), batch_size):
            batch = avis_sans_reponse[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(avis_sans_reponse) + batch_size - 1) // batch_size
            
            print(f"Batch {batch_num}/{total_batches} ({len(batch)} réponses)")
            
            for avis in batch:
                try:
                    row_data = {
                        "Nom": avis.profil or "",
                        "Titre de l'avis": avis.titre_review or "",
                        "Avis": avis.contenu or "",
                        "produit_titre_complet": avis.produit.titre if avis.produit else "",
                        "brand": avis.produit.marque if avis.produit else "",
                        "sentiment": avis.sentiment or "neutral",
                        "etoiles_valeur": avis.etoiles_valeur,
                    }
                    
                    reponse = pipeline.generate_response(row_data)
                    
                    mettre_a_jour_reponse(
                        db=db,
                        avis_id=int(avis.id),
                        reponse_generee=reponse,
                    )
                    
                    nb_reponses += 1
                    
                    if nb_reponses <= 3:
                        print(f"   Réponse #{nb_reponses}: {reponse[:80]}...")
                
                except Exception as e:
                    nb_erreurs += 1
                    print(f"   Erreur avis ID={avis.id}: {e}")
                    continue
            
            print(f"   -> {nb_reponses}/{nb_reponses_a_generer} générées\n")
            
            analysis_task_manager.update_progress(
                analysis_task_id,
                f"Réponses générées : {nb_reponses}/{nb_reponses_a_generer}"
            )
        
        print("=" * 80)
        print("GÉNÉRATION TERMINÉE")
        print(f"   - Réussis : {nb_reponses}/{nb_reponses_a_generer}")
        print(f"   - Erreurs : {nb_erreurs}")
        print("=" * 80 + "\n")
        
        # ========================================================================
        # EXPORT OPTIONNEL CSV/JSON
        # ========================================================================
        
        result_files: List[str] = []
        
        if output_csv or output_json:
            print("6. EXPORT DES FICHIERS")
            print("=" * 80)
            
            from app.config import settings
            
            # Créer le dossier de sortie
            results_dir = Path(settings.results_dir).resolve()
            results_dir.mkdir(parents=True, exist_ok=True)
            
            # Récupérer les avis avec réponses
            if scrape_task_id:
                tous_avis = db.query(Avis).join(SessionScraping).filter(
                    SessionScraping.task_id == scrape_task_id,
                    Avis.reponse_generee.isnot(None)
                ).all()
            else:
                tous_avis = db.query(Avis).filter(
                    Avis.reponse_generee.isnot(None)
                ).limit(nb_reponses_a_generer).all()
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_filename = f"reponses_{scrape_task_id or 'all'}_{timestamp}"
            
            # Export CSV
            if output_csv:
                csv_path = results_dir / f"{base_filename}.csv"
                
                with open(csv_path, "w", encoding="utf-8", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        "ID", "Produit", "Marque", "Auteur", "Titre", 
                        "Contenu", "Etoiles", "Sentiment", "Score Sentiment",
                        "Réponse Générée", "Date Scraping", "Date Analyse", "Date Réponse"
                    ])
                    
                    for avis in tous_avis:
                        writer.writerow([
                            avis.id,
                            avis.produit.titre if avis.produit else "",
                            avis.produit.marque if avis.produit else "",
                            avis.profil or "",
                            avis.titre_review or "",
                            avis.contenu or "",
                            avis.etoiles_valeur,
                            avis.sentiment,
                            avis.score_sentiment,
                            avis.reponse_generee or "",
                            avis.date_scraping,
                            avis.date_analyse,
                            avis.date_reponse,
                        ])
                
                result_files.append(str(csv_path))
                print(f"CSV exporté : {csv_path}")
            
            # Export JSON
            if output_json:
                json_path = results_dir / f"{base_filename}.json"
                
                export_data = {
                    "metadata": {
                        "task_id": scrape_task_id or "all",
                        "export_date": datetime.now().isoformat(),
                        "nb_avis": len(tous_avis),
                    },
                    "avis": [
                        {
                            "id": avis.id,
                            "produit": {
                                "titre": avis.produit.titre if avis.produit else "",
                                "marque": avis.produit.marque if avis.produit else "",
                                "url": avis.produit.url if avis.produit else "",
                            },
                            "auteur": avis.profil or "",
                            "titre": avis.titre_review or "",
                            "contenu": avis.contenu or "",
                            "etoiles": avis.etoiles_valeur,
                            "sentiment": avis.sentiment,
                            "score_sentiment": avis.score_sentiment,
                            "reponse_generee": avis.reponse_generee or "",
                            "dates": {
                                "scraping": avis.date_scraping.isoformat() if avis.date_scraping else None,
                                "analyse": avis.date_analyse.isoformat() if avis.date_analyse else None,
                                "reponse": avis.date_reponse.isoformat() if avis.date_reponse else None,
                            },
                        }
                        for avis in tous_avis
                    ]
                }
                
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(export_data, f, ensure_ascii=False, indent=2)
                
                result_files.append(str(json_path))
                print(f"JSON exporté : {json_path}")
            
            print("=" * 80 + "\n")
        
        # ========================================================================
        
        result_file = result_files[0] if result_files else "Réponses générées dans la BDD"
        analysis_task_manager.set_result(analysis_task_id, result_file)
        analysis_task_manager.update_status(analysis_task_id, "completed")
        
        target_msg = f"session '{scrape_task_id}'" if scrape_task_id else "tous les avis"
        analysis_task_manager.update_progress(
            analysis_task_id,
            f"Génération terminée pour {target_msg} : {nb_reponses} réponses"
        )

    except Exception as e:
        print(f"\nERREUR : {e}")
        analysis_task_manager.update_status(analysis_task_id, "failed")
        analysis_task_manager.set_error(analysis_task_id, str(e))
        import traceback
        traceback.print_exc()
    
    finally:
        if db:
            db.close()