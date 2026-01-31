from app.database import drop_all_tables, init_database

print("⚠️ Suppression de toutes les tables...")
drop_all_tables()

print("✅ Recréation des tables avec la nouvelle structure...")
init_database()

print("✅ Base de données réinitialisée avec task_id!")