import os
from app.config import settings
from app.core.analysis_task_manager import analysis_task_manager

from app.database import SessionLocal
from app.crud import (
    get_session_by_task_id,
    get_avis_non_analyses_by_task_id,
    get_avis_sans_reponse_by_task_id,
    recuperer_avis_non_analyses,
    recuperer_avis_sans_reponse,
    mettre_a_jour_sentiment,
    mettre_a_jour_reponse,
    recuperer_avis,
)


# ============================================================================
# FONCTION 1 : ANALYSE DE SENTIMENT UNIQUEMENT
# ============================================================================

def execute_sentiment_analysis_task(
    analysis_task_id: str,
    scrape_task_id: str | None,
    use_gpu: bool,
):
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
        print("1️Initialisation de la session BDD...")
        db = SessionLocal()
        print("Session BDD créée\n")
        
        analysis_task_manager.update_status(analysis_task_id, "running")
        
        # Mode ciblé ou global
        if scrape_task_id:
            print(f"2️MODE CIBLÉ : session '{scrape_task_id}'")
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
            print("2️MODE GLOBAL : tous les avis non analysés")
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
        print("3️CHARGEMENT DU PIPELINE")
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
        
        print("\n⏳ Chargement du pipeline...")
        pipeline = get_cached_pipeline(use_gpu=use_gpu)
        print("PIPELINE CHARGÉ !\n")
        
        # Analyse de sentiment
        print("4️ANALYSE DE SENTIMENT")
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
                    sentiment_result = pipeline.analyze_sentiment(avis.contenu)
                    
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
                        avis_id=avis.id,
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
            
            print(f"   → {nb_analyses}/{nb_avis} analysés\n")
            
            analysis_task_manager.update_progress(
                analysis_task_id,
                f"🔍 Sentiment analysé : {nb_analyses}/{nb_avis}"
            )
        
        print("=" * 80)
        print(f"ANALYSE TERMINÉE")
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
    scrape_task_id: str | None,
    use_gpu: bool,
    output_csv: bool,
    output_json: bool,
):
    """
    Exécute UNIQUEMENT la génération de réponses (pas d'analyse de sentiment).
    Remplit les colonnes : reponse_generee, date_reponse, statut='responded'
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
        print("1️Initialisation de la session BDD...")
        db = SessionLocal()
        print("Session BDD créée\n")
        
        analysis_task_manager.update_status(analysis_task_id, "running")
        
        # Mode ciblé ou global
        if scrape_task_id:
            print(f"2️MODE CIBLÉ : session '{scrape_task_id}'")
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
            print("2️MODE GLOBAL : tous les avis sans réponse")
            analysis_task_manager.update_progress(
                analysis_task_id,
                "Mode global : tous les avis sans réponse"
            )
            
            avis_sans_reponse = recuperer_avis_sans_reponse(db, limite=10000)
        
        print(f"{len(avis_sans_reponse)} avis sans réponse\n")
        
        if not avis_sans_reponse:
            print("⚠️ AUCUNE RÉPONSE À GÉNÉRER")
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
        print("3️CHARGEMENT DU PIPELINE")
        print("=" * 80)
        
        analysis_task_manager.update_progress(
            analysis_task_id,
            "Chargement du modèle de génération…",
        )
        
        from app.core.review_pipeline import get_cached_pipeline
        import torch
        
        print(f"🔍 CUDA disponible : {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"🎮 GPU détecté : {torch.cuda.get_device_name(0)}")
        
        print("\n⏳ Chargement du pipeline...")
        pipeline = get_cached_pipeline(use_gpu=use_gpu)
        print("PIPELINE CHARGÉ !\n")
        
        # Génération de réponses
        print("4️GÉNÉRATION DE RÉPONSES")
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
                        avis_id=avis.id,
                        reponse_generee=reponse,
                    )
                    
                    nb_reponses += 1
                    
                    if nb_reponses <= 3:
                        print(f"   Réponse #{nb_reponses}: {reponse[:80]}...")
                
                except Exception as e:
                    nb_erreurs += 0
                    print(f"   Erreur avis ID={avis.id}: {e}")
                    continue
            
            print(f"   → {nb_reponses}/{nb_reponses_a_generer} générées\n")
            
            analysis_task_manager.update_progress(
                analysis_task_id,
                f"Réponses générées : {nb_reponses}/{nb_reponses_a_generer}"
            )
        
        print("=" * 80)
        print(f"GÉNÉRATION TERMINÉE")
        print(f"   - Réussis : {nb_reponses}/{nb_reponses_a_generer}")
        print(f"   - Erreurs : {nb_erreurs}")
        print("=" * 80 + "\n")
        
        # Export optionnel (même code que avant)
        result_files = []
        
        if output_csv or output_json:
            # ... (même code d'export que dans ta version précédente)
            pass
        
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