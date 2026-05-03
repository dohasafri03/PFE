import sqlite3
import psycopg2
from psycopg2.extras import execute_batch
import os
import hashlib
from dotenv import load_dotenv
import logging

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Chargement forcé des variables d'environnement (écrase le cache Windows)
load_dotenv(override=True)

# Utiliser les .env ou définir par défaut
SQLITE_DB_PATH = os.getenv("SQLITE_DB", "data/marche_ai.sqlite3")
DATABASE_URL = os.getenv("DATABASE_URL")

import urllib.parse
try:
    __parsed = urllib.parse.urlparse(DATABASE_URL)
    logger.info(f"🔍 [DEBUG] URL reconnue -> Utilisateur: {__parsed.username} | Base: {__parsed.path.lstrip('/')}")
except:
    pass

def connect_sqlite():
    """Connecte à la base de données SQLite."""
    try:
        if not os.path.exists(SQLITE_DB_PATH):
            raise FileNotFoundError(f"Le fichier {SQLITE_DB_PATH} n'existe pas.")
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        logger.info(f"✅ Connecté à SQLite: {SQLITE_DB_PATH}")
        return conn
    except Exception as e:
        logger.error(f"❌ Erreur connexion SQLite: {e}")
        raise

def connect_postgres():
    """Connecte à la base de données PostgreSQL via DATABASE_URL."""
    if not DATABASE_URL:
        raise ValueError("❌ DATABASE_URL n'est pas défini dans le fichier .env")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        logger.info("✅ Connecté à PostgreSQL")
        return conn
    except Exception as e:
        logger.error(f"❌ Erreur connexion PostgreSQL: {e}")
        raise

def map_sqlite_type_to_postgres(sqlite_type, column_name):
    """Mappe les types de données SQLite vers PostgreSQL."""
    t = sqlite_type.upper()
    if column_name.lower() == 'id':
        return 'SERIAL PRIMARY KEY'
    
    if 'INT' in t:
        return 'INTEGER'
    elif 'CHAR' in t or 'CLOB' in t or 'TEXT' in t or t == '':
        return 'TEXT'
    elif 'REAL' in t or 'FLOA' in t or 'DOUB' in t:
        return 'FLOAT'
    elif 'DATE' in t or 'TIME' in t:
        return 'TIMESTAMP'
    elif 'BOOL' in t:
        return 'BOOLEAN'
    elif 'BLOB' in t:
        return 'BYTEA'
    else:
        return 'TEXT'

def migrate_table(sqlite_conn, pg_conn, table_name):
    """Migre une table spécifique avec recréation de schéma et insertion par lots."""
    logger.info(f"🔄 Début migration de la table : {table_name}")
    
    sqlite_cursor = sqlite_conn.cursor()
    pg_cursor = pg_conn.cursor()
    
    try:
        # --- 1. Lire la structure SQLite ---
        sqlite_cursor.execute(f"PRAGMA table_info({table_name});")
        columns_info = sqlite_cursor.fetchall()
        
        if not columns_info:
            logger.warning(f"⚠️ Table {table_name} vide ou inexistante dans SQLite.")
            return 0
            
        columns_def = []
        col_names = []
        
        for col in columns_info:
            col_name = col['name']
            sqlite_type = col['type']
            not_null = "NOT NULL" if col['notnull'] else ""
            default = f"DEFAULT {col['dflt_value']}" if col['dflt_value'] else ""
            pg_type = map_sqlite_type_to_postgres(sqlite_type, col_name)
            
            columns_def.append(f"{col_name} {pg_type} {not_null} {default}".strip())
            col_names.append(col_name)
            
        # [BONUS] Ajouter le champ hash s'il est absent de la table des opportunités
        is_opp_table = table_name.lower() in ('opportunities', 'appels_offres')
        if is_opp_table and 'hash' not in col_names:
            columns_def.append("hash TEXT UNIQUE")
            col_names.append('hash')
            logger.info("✨ Bonus : Ajout du champ 'hash' dans la table des opportunités")

        # --- 2. Créer la table dans PostgreSQL ---
        pg_cursor.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE;")
        create_table_sql = f"CREATE TABLE {table_name} ({', '.join(columns_def)});"
        pg_cursor.execute(create_table_sql)
        logger.info(f"✅ Schéma validé et recréé pour {table_name}.")
        
        # --- 3. Ajouter les Index & Contraintes ---
        if is_opp_table:
            # Votre colonne de référence s'appelle sûrement 'ref' ou 'reference'
            ref_col = 'ref' if 'ref' in col_names else 'reference' if 'reference' in col_names else None
            if ref_col:
                try:
                    pg_cursor.execute(f"ALTER TABLE {table_name} ADD CONSTRAINT unique_{ref_col} UNIQUE ({ref_col});")
                except Exception:
                    pass
            
            # Index sur profile (ou service) et level (priority)
            for idx_col in ['level', 'priority', 'service', 'profile']:
                if idx_col in col_names:
                    try:
                        pg_cursor.execute(f"CREATE INDEX idx_{table_name}_{idx_col} ON {table_name} ({idx_col});")
                    except Exception:
                        pass
                
        # --- 4. Extraire les données de SQLite ---
        sqlite_cursor.execute(f"SELECT * FROM {table_name};")
        rows = sqlite_cursor.fetchall()
        
        if not rows:
            logger.info(f"ℹ️ Aucun enregistrement trouvé dans {table_name}.")
            pg_conn.commit()
            return 0
            
        # --- 5. Transformer et préparer le Batch Insert ---
        insert_cols = col_names
        placeholders = ", ".join(["%s"] * len(insert_cols))
        # Remplacement clé : ON CONFLICT DO NOTHING pour ignorer les duplications futures
        insert_sql = f"INSERT INTO {table_name} ({', '.join(insert_cols)}) VALUES ({placeholders}) ON CONFLICT DO NOTHING;"
        
        # Identifier les colonnes booléennes pour les caster (SQLite retourne 0/1, Postgres veut True/False)
        bool_cols = [col_names[i] for i, df in enumerate(columns_def) if 'BOOLEAN' in df.upper()]
        
        data_to_insert = []
        for row in rows:
            row_dict = dict(row)
            
            # Application du hash si l'opportunité n'en a pas
            if is_opp_table and 'hash' in insert_cols and not row_dict.get('hash'):
                t = str(row_dict.get('title', ''))
                b = str(row_dict.get('buyer', row_dict.get('organisme', '')))
                row_dict['hash'] = hashlib.sha256(f"{t}{b}".encode()).hexdigest()
            
            # Typage explicite pour PostgreSQL
            for c in bool_cols:
                if row_dict.get(c) is not None:
                    row_dict[c] = bool(row_dict[c])
                    
            data_tuple = tuple(row_dict.get(c) for c in insert_cols)
            data_to_insert.append(data_tuple)
            
        # --- 6. Exécution optimisée ---
        try:
            execute_batch(pg_cursor, insert_sql, data_to_insert, page_size=2000)
            pg_conn.commit()
            logger.info(f"✅ {len(data_to_insert)} lignes parfaitement migrées vers {table_name}.")
            return len(data_to_insert)
        except Exception as e:
            pg_conn.rollback() # Rollback de sécurité
            logger.error(f"❌ Erreur lors de l'insertion dans {table_name}: {e}")
            raise

    except Exception as e:
        pg_conn.rollback()
        logger.error(f"❌ Erreur critique sur la table {table_name}: {e}")
        raise
    finally:
        pg_cursor.close()

def main():
    logger.info("🚀 --- Démarrage de la Migration vers PostgreSQL ---")
    sqlite_conn = None
    pg_conn = None
    
    try:
        sqlite_conn = connect_sqlite()
        pg_conn = connect_postgres()
        
        # Liste de toutes les tables natives de SQLite
        cursor = sqlite_conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = [row['name'] for row in cursor.fetchall()]
        
        total_migrated = {}
        for table in tables:
            migrated_count = migrate_table(sqlite_conn, pg_conn, table)
            total_migrated[table] = migrated_count
            
        # --- 7. Bilan et Vérification finale ---
        logger.info("\n📊 --- RAPPORT DE MIGRATION ---")
        for table, count in total_migrated.items():
            logger.info(f"  ❯ {table} : {count} lignes insérées.")
            
        if any(t in total_migrated for t in ['opportunities', 'appels_offres']):
            nb_opp = total_migrated.get('opportunities', total_migrated.get('appels_offres', 0))
            if nb_opp > 0:
                logger.info(f"✅ Vérification : La table principale d'opportunités est remplie ({nb_opp} lignes) !")
            else:
                logger.warning("⚠️ Attention, la table des opportunités semble vide.")
            
        logger.info("\n🎉 Migration terminée avec succès !")

    except Exception as e:
        logger.error(f"🚨 La migration s'est arrêtée suite à une erreur : {e}")
    finally:
        # Fermeture propre des bases
        if sqlite_conn:
            sqlite_conn.close()
        if pg_conn:
            pg_conn.close()

if __name__ == "__main__":
    main()