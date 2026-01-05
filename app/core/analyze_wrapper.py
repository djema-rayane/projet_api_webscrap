import os
from app.config import settings
from app.core.analysis_task_manager import analysis_task_manager


def execute_analysis_task(analysis_task_id: str, scrape_task_id: str, use_gpu: bool, output_csv: bool, output_json: bool):
    try:
        analysis_task_manager.update_status(analysis_task_id, "running")
        analysis_task_manager.update_progress(analysis_task_id, "Chargement du JSON de scraping…")

        input_json = os.path.join(settings.results_dir, f"amazon_reviews_{scrape_task_id}.json")
        if not os.path.exists(input_json):
            raise FileNotFoundError(f"Fichier JSON de scraping introuvable: {input_json}")

        out_dir = os.path.join(settings.results_dir, "analysis")
        os.makedirs(out_dir, exist_ok=True)

        # On génère un CSV
        output_csv_path = os.path.join(out_dir, f"reviews_with_responses_{analysis_task_id}.csv")

        analysis_task_manager.update_progress(analysis_task_id, "Chargement des modèles + analyse sentiment + génération réponses…")

        # Import ici pour éviter de charger les modèles au démarrage du serveur
        from app.core.review_pipeline import process_reviews_from_json

        # Lance le pipeline complet (JSON -> sentiment -> réponses -> CSV)
        df = process_reviews_from_json(
            json_file=input_json,
            output_csv=output_csv_path,
            use_gpu=use_gpu
        )

        # Optionnel: sortir aussi un JSON enrichi
        if output_json:
            analysis_task_manager.update_progress(analysis_task_id, "Export JSON enrichi…")
            output_json_path = os.path.join(out_dir, f"reviews_with_responses_{analysis_task_id}.json")
            df.to_json(output_json_path, orient="records", force_ascii=False, indent=2)

        analysis_task_manager.set_result(analysis_task_id, output_csv_path)
        analysis_task_manager.update_status(analysis_task_id, "completed")
        analysis_task_manager.update_progress(analysis_task_id, "Analyse terminée ✅")

    except Exception as e:
        analysis_task_manager.update_status(analysis_task_id, "failed")
        analysis_task_manager.set_error(analysis_task_id, str(e))
