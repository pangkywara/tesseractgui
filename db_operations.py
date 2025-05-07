import sqlite3
import logging
import json
import os
from datetime import datetime
import cv2 # For image processing
import numpy as np # cv2 often works with numpy arrays

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
    """Creates the ocr_results table if it doesn't exist and adds image_blob column if missing."""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            # Skema tabel setelah penghapusan kolom confidence dan word_boxes
            # Added image_blob BLOB
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
                    tessdata_dir TEXT,
                    image_blob BLOB 
                )
            """)
            conn.commit()
            logging.info("Table 'ocr_results' checked/created successfully.")

            # Check if image_blob column exists and add it if not
            cursor.execute("PRAGMA table_info(ocr_results);")
            columns = [column['name'] for column in cursor.fetchall()]
            if 'image_blob' not in columns:
                cursor.execute("ALTER TABLE ocr_results ADD COLUMN image_blob BLOB;")
                conn.commit()
                logging.info("Column 'image_blob' added to 'ocr_results' table.")

        except sqlite3.Error as e:
            logging.error(f"Error creating/checking table 'ocr_results': {e}")
        finally:
            conn.close()

# Ensure table exists when module is loaded
create_table_if_not_exists()

# OOP: Abstraksi - Menyembunyikan detail SQL DML (Data Manipulation Language) untuk menyimpan data.
def save_ocr_result_to_db(result_data):
    """Saves OCR result data (dictionary) and an image thumbnail to the SQLite database."""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            # Pernyataan INSERT yang diperbarui tanpa confidence dan word_boxes, added image_blob
            sql = """
                INSERT INTO ocr_results (filename, language, psm, oem, detected_text, image_path, preproc_config, tessdata_dir, image_blob)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            # Serialisasi preproc_config ke JSON jika berupa dictionary
            preproc_config_json = json.dumps(result_data.get('preproc_config')) if isinstance(result_data.get('preproc_config'), dict) else result_data.get('preproc_config')

            # Process and store thumbnail
            image_bytes = None
            image_path = result_data.get('image_path')
            if image_path and os.path.exists(image_path):
                try:
                    img = cv2.imread(image_path)
                    if img is not None:
                        max_width = 150 # Max width for thumbnail
                        height, width = img.shape[:2]
                        if width > max_width:
                            scale_ratio = max_width / width
                            new_width = max_width
                            new_height = int(height * scale_ratio)
                            thumbnail = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_AREA)
                        else:
                            thumbnail = img
                        
                        # Encode to JPEG format, quality 85
                        success, encoded_image = cv2.imencode('.jpg', thumbnail, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                        if success:
                            image_bytes = encoded_image.tobytes()
                        else:
                            logging.warning(f"Could not encode thumbnail for {image_path}")
                    else:
                        logging.warning(f"Could not read image for thumbnail: {image_path} (cv2.imread returned None)")
                except Exception as e:
                    logging.error(f"Error processing image for thumbnail {image_path}: {e}")
            else:
                logging.warning(f"Image path not found or not provided for thumbnail generation: {image_path}")


            # Tuple nilai yang diperbarui
            values = (
                result_data.get('filename'),
                result_data.get('language'),
                result_data.get('psm'),
                result_data.get('oem'),
                result_data.get('detected_text'),
                result_data.get('image_path'),
                preproc_config_json,
                result_data.get('tessdata_dir'),
                image_bytes # Add image blob here
            )
            # ---- ADDING DIAGNOSTIC LOGGING ----
            logging.info(f"[DB_SAVE_DIAGNOSTIC] Saving detected_text: '{result_data.get('detected_text')[:100]}...'") # Log first 100 chars
            # ---- END DIAGNOSTIC LOGGING ----
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
    """Fetches all results from the ocr_results table, including image_blob."""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            # Query SELECT yang diperbarui tanpa confidence, added image_blob
            cursor.execute("SELECT id, timestamp, filename, language, psm, oem, detected_text, image_path, preproc_config, tessdata_dir, image_blob FROM ocr_results ORDER BY timestamp DESC")
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

ALLOWED_UPDATE_COLUMNS = ["filename", "language", "psm", "oem", "detected_text", "image_path", "preproc_config", "tessdata_dir"]

def update_ocr_record_field(record_id: int, field_name: str, new_value):
    """Updates a specific field for a given record ID in the ocr_results table.

    Args:
        record_id (int): The ID of the record to update.
        field_name (str): The name of the column to update.
        new_value: The new value for the field.

    Returns:
        tuple[bool, str]: (True, success_message) if update was successful, 
                          (False, error_message) otherwise.
    """
    if field_name not in ALLOWED_UPDATE_COLUMNS:
        logging.error(f"Attempt to update an invalid or restricted column: {field_name}")
        return False, f"Kolom '{field_name}' tidak dapat diubah."

    conn = get_db_connection()
    if not conn:
        return False, "Gagal terhubung ke database."

    try:
        cursor = conn.cursor()
        # Construct the SQL query safely
        # Note: field_name is checked against a whitelist, so direct inclusion in the query string is safe here.
        sql = f"UPDATE ocr_results SET {field_name} = ? WHERE id = ?"
        
        # Handle specific data types if necessary, e.g., JSON for preproc_config
        processed_value = new_value
        if field_name == "preproc_config":
            if isinstance(new_value, dict):
                processed_value = json.dumps(new_value)
            elif not isinstance(new_value, str):
                 # Attempt to convert to string if not already a dict or string
                processed_value = str(new_value) 
        
        # For PSM and OEM, ensure they are integers if they are passed as strings from UI
        if field_name in ["psm", "oem"]:
            try:
                processed_value = int(new_value)
            except ValueError:
                logging.error(f"Invalid value for {field_name}: '{new_value}'. Must be an integer.")
                return False, f"Nilai untuk '{field_name}' harus berupa angka integer."

        cursor.execute(sql, (processed_value, record_id))
        conn.commit()

        if cursor.rowcount > 0:
            logging.info(f"Record ID {record_id}, field '{field_name}' updated to '{processed_value}'.")
            return True, f"Data '{field_name}' berhasil diperbarui."
        else:
            logging.warning(f"No record found with ID {record_id} to update, or value was the same.")
            # It could be that the value was the same, so rowcount is 0. This isn't strictly an error.
            # For simplicity, we can return True if no exception, assuming intent was met or no change needed.
            # Or, treat as warning/no-op: return True, "Tidak ada data yang diubah (mungkin nilainya sama)."
            return False, f"Tidak ada data dengan ID {record_id} yang ditemukan atau nilai sama."

    except sqlite3.Error as e:
        logging.error(f"SQLite error updating record ID {record_id}, field {field_name}: {e}")
        conn.rollback()
        return False, f"Kesalahan SQLite: {e}"
    except Exception as e:
        logging.error(f"Unexpected error updating record ID {record_id}, field {field_name}: {e}")
        conn.rollback() # Should not be needed if sqlite3.Error caught it, but good practice
        return False, f"Kesalahan tak terduga: {e}"
    finally:
        if conn:
            conn.close() 
