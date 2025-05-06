import sqlite3
import logging
import json
import os
from datetime import datetime

DATABASE_FILE = os.path.join(os.path.dirname(__file__), "ocr_history.db")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# OOP: Abstraksi - Menyembunyikan detail koneksi ke basis data SQLite.
def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        conn.row_factory = sqlite3.Row
        logging.info("Successfully connected to SQLite database.")
        return conn
    except sqlite3.Error as e:
        logging.error(f"Error connecting to SQLite database: {e}")
        return None

# OOP: Abstraksi - Menyembunyikan detail SQL DDL (Data Definition Language) untuk membuat tabel.
def create_table_if_not_exists():
    """Creates the ocr_results table if it doesn't exist."""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            # Skema tabel setelah penghapusan kolom confidence dan word_boxes
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ocr_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    filename TEXT NOT NULL,
                    language TEXT,
                    psm INTEGER,
                    oem INTEGER,
                    detected_text TEXT,
                    image_path TEXT,
                    preproc_config TEXT,
                    tessdata_dir TEXT
                )
            """)
            conn.commit()
            logging.info("Table 'ocr_results' checked/created successfully.")
        except sqlite3.Error as e:
            logging.error(f"Error creating/checking table 'ocr_results': {e}")
        finally:
            conn.close()

# Ensure table exists when module is loaded
create_table_if_not_exists()

# OOP: Abstraksi - Menyembunyikan detail SQL DML (Data Manipulation Language) untuk menyimpan data.
def save_ocr_result_to_db(result_data):
    """Saves OCR result data (dictionary) to the SQLite database."""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            # Pernyataan INSERT yang diperbarui tanpa confidence dan word_boxes
            sql = """
                INSERT INTO ocr_results (filename, language, psm, oem, detected_text, image_path, preproc_config, tessdata_dir)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            # Serialisasi preproc_config ke JSON jika berupa dictionary
            preproc_config_json = json.dumps(result_data.get('preproc_config')) if isinstance(result_data.get('preproc_config'), dict) else result_data.get('preproc_config')

            # Tuple nilai yang diperbarui
            values = (
                result_data.get('filename'),
                result_data.get('language'),
                result_data.get('psm'),
                result_data.get('oem'),
                result_data.get('detected_text'),
                result_data.get('image_path'),
                preproc_config_json,
                result_data.get('tessdata_dir')
            )
            cursor.execute(sql, values)
            conn.commit()
            logging.info(f"Successfully saved OCR result for {result_data.get('filename')} to SQLite.")
            return cursor.lastrowid
        except sqlite3.Error as e:
            logging.error(f"Error saving OCR result to SQLite: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()
    return None

# OOP: Abstraksi - Menyembunyikan detail query SELECT untuk mengambil semua riwayat.
def fetch_all_results():
    """Fetches all results from the ocr_results table."""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            # Query SELECT yang diperbarui tanpa confidence
            cursor.execute("SELECT id, timestamp, filename, language, psm, oem, detected_text, image_path, preproc_config, tessdata_dir FROM ocr_results ORDER BY timestamp DESC")
            results = cursor.fetchall()
            results_list = [dict(row) for row in results]
            logging.info(f"Fetched {len(results_list)} results from SQLite.")
            return results_list
        except sqlite3.Error as e:
            logging.error(f"Error fetching results from SQLite: {e}")
            return []
        finally:
            conn.close()
    return []

# OOP: Abstraksi - Menyembunyikan detail query DELETE untuk menghapus berdasarkan ID.
def delete_result_by_id(result_id):
    """Deletes a specific result by its ID."""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM ocr_results WHERE id = ?", (result_id,))
            conn.commit()
            if cursor.rowcount > 0:
                logging.info(f"Successfully deleted result with ID {result_id} from SQLite.")
                return True
            else:
                logging.warning(f"No result found with ID {result_id} to delete.")
                return False
        except sqlite3.Error as e:
            logging.error(f"Error deleting result with ID {result_id} from SQLite: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    return False

# OOP: Abstraksi - Menyembunyikan detail query DELETE untuk menghapus semua data.
def clear_all_ocr_results():
    """Deletes all records from the ocr_results table."""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM ocr_results")
            # Optionally, to reset the autoincrement counter for ID (for SQLite):
            # cursor.execute("DELETE FROM sqlite_sequence WHERE name='ocr_results'")
            conn.commit()
            logging.info("Successfully deleted all records from 'ocr_results'.")
            # Get the number of deleted rows, though DELETE without WHERE doesn't directly return it for all DBs
            # For SQLite, changes() reflects the number of rows affected by the last INSERT, UPDATE, or DELETE statement.
            # We can infer this by re-querying count or checking changes() if needed, but for now, just log success.
            return True # Indicate success
        except sqlite3.Error as e:
            logging.error(f"Error clearing table 'ocr_results': {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    return False 