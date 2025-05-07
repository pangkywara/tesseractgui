import sys
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, 
    QPushButton, QAbstractItemView, QHeaderView, QMessageBox, QLabel, QMenu
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QPixmap, QImage
import traceback
import datetime
import json # For parsing preproc_config if needed for display
import logging

# Import the fetch function - db_operations.py now has fetch_all_results that doesn't fetch confidence
from .db_operations import fetch_all_results, delete_result_by_id, update_ocr_record_field # Added update_ocr_record_field

# OOP: Inheritance (Pewarisan) - Mewarisi dari QThread untuk pekerjaan latar belakang.
# OOP: Abstraksi - Menyembunyikan detail pengambilan data DB dari HistoryWindow.
class DbFetchWorker(QThread):
    results_ready = Signal(list) # Emit list of tuples/rows
    fetch_error = Signal(str)    # Emit error message

    def __init__(self, parent=None):
        super().__init__(parent)

    # OOP: Polymorphism (Polimorfisme) - Override metode run() dari QThread.
    def run(self):
        """Calls the fetch function in the background."""
        try:
            print("DbFetchWorker: Fetching results...")
            results = fetch_all_results()
            print(f"DbFetchWorker: Fetched {len(results)} results.")
            self.results_ready.emit(results)
        except Exception as e:
            traceback.print_exc()
            error_msg = f"Kesalahan Pengambilan DB: {type(e).__name__}: {e}"
            print(f"DbFetchWorker: {error_msg}")
            self.fetch_error.emit(error_msg)

# OOP: Inheritance (Pewarisan) - Mewarisi fungsionalitas window dialog dari QDialog.
# OOP: Encapsulation (Enkapsulasi) - Mengelola widget (tabel, tombol, label) dan data riwayat.
class HistoryWindow(QDialog):
    # OOP: Encapsulation (Enkapsulasi) - Konstanta internal untuk mapping kolom.
    # Adjusted column headers: removed 'Confidence', added 'Preproc Config', 'Tessdata Dir'
    # The order should match the SELECT statement in db_operations.fetch_all_results implicitly via dict keys
    # Keys from dict(row) in fetch_all_results are: id, timestamp, filename, language, psm, oem, detected_text, image_path, preproc_config, tessdata_dir
    
    # We will define the display order and headers here explicitly
    # And then map the dictionary keys to these columns
    COLUMN_MAPPING = {
        "ID": "id",
        "Waktu": "timestamp", # Timestamp
        "Pratinjau": "image_blob", # New column for image preview
        "Nama Berkas": "filename", # Filename
        "Bahasa": "language", # Language
        "PSM": "psm",
        "OEM": "oem",
        "Teks Terdeteksi": "detected_text", # Detected Text
        # "Image Path": "image_path", # Usually too long for direct display
        "Pra-pemrosesan": "preproc_config", # Preprocessing
        "Direktori Tessdata": "tessdata_dir" # Tessdata Dir
    }
    
    EDITABLE_COLUMNS = ["Nama Berkas", "Teks Terdeteksi", "Bahasa", "PSM", "OEM"] # Columns that can be edited by the user
    # Define which columns are numeric for potential validation (not strictly enforced in this version)
    NUMERIC_COLUMNS = ["PSM", "OEM"]

    # OOP: Encapsulation (Enkapsulasi) - Define which columns to initially hide for brevity
    HIDDEN_COLUMNS = ["Direktori Tessdata", "Pra-pemrosesan"]

    # OOP: Encapsulation (Enkapsulasi) - Inisialisasi state internal dan widget.
    def __init__(self, parent=None):
        super().__init__(parent)
        self.fetch_worker: DbFetchWorker | None = None

        self.setWindowTitle("Riwayat OCR") # Window Title
        self.setMinimumSize(800, 500)
        self.setModal(False) # Allow interaction with main window

        # --- Layout --- # 
        layout = QVBoxLayout(self)
        
        # --- Controls --- #
        controls_layout = QHBoxLayout()
        self.refresh_button = QPushButton("Segarkan") # Refresh
        self.refresh_button.clicked.connect(self.load_history)
        self.status_label = QLabel("Memuat riwayat...") # Loading history...
        controls_layout.addWidget(self.refresh_button)
        controls_layout.addWidget(self.status_label, 1) # Stretch label
        controls_layout.addStretch()
        layout.addLayout(controls_layout)

        # --- Table Widget --- #
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(len(self.COLUMN_MAPPING))
        self.table_widget.setHorizontalHeaderLabels(list(self.COLUMN_MAPPING.keys()))
        
        # Set a default row height to accommodate thumbnails
        self.table_widget.verticalHeader().setDefaultSectionSize(100) # Adjust as needed (e.g., 100-120px)
        self.table_widget.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed) # Or Interactive / ResizeToContents

        # Enable editing: Double click or any key press on a selected item
        self.table_widget.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked | 
            QAbstractItemView.EditTrigger.SelectedClicked | 
            QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        self.table_widget.itemChanged.connect(self.handle_item_changed) # Connect signal

        self.table_widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_widget.setAlternatingRowColors(True)
        self.table_widget.verticalHeader().setVisible(False) # Hide row numbers
        self.table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_widget.horizontalHeader().setStretchLastSection(True)

        # Context menu for deleting rows
        self.table_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_widget.customContextMenuRequested.connect(self.show_table_context_menu)

        layout.addWidget(self.table_widget)

        # --- Initial Load --- #
        self.load_history()
        # self._hide_columns() # Will be called after populating table

    # OOP: Encapsulation (Enkapsulasi) - Metode internal untuk mengelola menu konteks.
    def show_table_context_menu(self, pos):
        menu = QMenu()
        delete_action = menu.addAction("Hapus Baris Terpilih") # Delete Selected Row(s)
        action = menu.exec(self.table_widget.mapToGlobal(pos))
        if action == delete_action:
            self.delete_selected_rows()

    # OOP: Encapsulation (Enkapsulasi) - Metode untuk mengelola state (menghapus data).
    # OOP: Abstraksi - Menyembunyikan detail interaksi dengan db_operations.delete_result_by_id.
    def delete_selected_rows(self):
        selected_rows = sorted(list(set(index.row() for index in self.table_widget.selectedIndexes())), reverse=True)
        if not selected_rows:
            QMessageBox.information(self, "Tidak Ada Pilihan", "Silakan pilih baris untuk dihapus.") # No Selection, Please select row(s) to delete.
            return

        reply = QMessageBox.question(self, "Konfirmasi Hapus", 
                                     f"Apakah Anda yakin ingin menghapus {len(selected_rows)} data terpilih?", # Are you sure you want to delete {len(selected_rows)} selected record(s)?
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            deleted_count = 0
            for row_idx in selected_rows:
                id_item = self.table_widget.item(row_idx, list(self.COLUMN_MAPPING.keys()).index("ID"))
                if id_item:
                    result_id = int(id_item.text())
                    if delete_result_by_id(result_id):
                        self.table_widget.removeRow(row_idx)
                        deleted_count += 1
                    else:
                        QMessageBox.warning(self, "Kesalahan Hapus", f"Gagal menghapus data dengan ID {result_id}.") # Delete Error, Failed to delete record with ID {result_id}.
            if deleted_count > 0:
                self.status_label.setText(f"Berhasil menghapus {deleted_count} data.") # Deleted {deleted_count} record(s).

    # OOP: Encapsulation (Enkapsulasi) - Mengelola state (memulai pengambilan data).
    def load_history(self):
        """Starts the background worker to fetch history data."""
        if self.fetch_worker and self.fetch_worker.isRunning():
            print("Fetch worker already running.")
            return # Don't start another fetch if one is active
        
        self.table_widget.setRowCount(0) # Clear table
        self.status_label.setText("Mengambil data dari database...") # Fetching data from database...
        self.refresh_button.setEnabled(False)
        
        self.fetch_worker = DbFetchWorker(self)
        self.fetch_worker.results_ready.connect(self.populate_table)
        self.fetch_worker.fetch_error.connect(self.handle_fetch_error)
        self.fetch_worker.finished.connect(self.fetch_finished)
        self.fetch_worker.start()

    # OOP: Encapsulation (Enkapsulasi) - Metode slot untuk menerima hasil dari worker.
    def populate_table(self, results: list[dict]): # results is now a list of dicts
        """Fills the table widget with fetched data."""
        self.table_widget.blockSignals(True) # Block signals during programmatic changes
        self.table_widget.setRowCount(0) # Clear existing rows before populating
        self.table_widget.setRowCount(len(results))
        column_names = list(self.COLUMN_MAPPING.keys())

        for row_idx, row_data_dict in enumerate(results):
            for col_idx, display_header in enumerate(column_names):
                db_key = self.COLUMN_MAPPING[display_header]
                item_data = row_data_dict.get(db_key)
                
                display_text = ""
                if item_data is None:
                    display_text = "-"
                elif isinstance(item_data, datetime.datetime):
                    display_text = item_data.strftime("%Y-%m-%d %H:%M:%S")
                elif isinstance(item_data, bool):
                    display_text = "Ya" if item_data else "Tidak" # Yes/No
                elif db_key == "preproc_config": # Key for preprocessing (matches COLUMN_MAPPING)
                    try:
                        # Ensure item_data is a dict for consistent processing
                        data_dict = {}
                        if isinstance(item_data, str) and item_data.strip():
                            try:
                                data_dict = json.loads(item_data)
                            except json.JSONDecodeError:
                                print(f"Warning: Could not parse preproc_config JSON string: {item_data}")
                                data_dict = {} # Keep it as empty dict
                        elif isinstance(item_data, dict):
                            data_dict = item_data
                        
                        if data_dict: # Check if data_dict is not None and not empty
                            translated_preproc = []
                            if data_dict.get('apply_deskew'): translated_preproc.append("Koreksi Kemiringan")
                            if data_dict.get('apply_clahe'): translated_preproc.append("CLAHE")
                            if data_dict.get('apply_spellcheck'): translated_preproc.append("Periksa Ejaan")
                            blur = data_dict.get('blur_type', 'None')
                            if blur != 'None': translated_preproc.append(f"Blur: {blur}")
                            display_text = ", ".join(translated_preproc) if translated_preproc else "Tidak ada"
                        else: # Handles None, empty string, or empty dict after parsing
                            display_text = "Tidak ada" 
                    except Exception as e: # Catch any error during preproc display
                        display_text = str(item_data) # Fallback
                        print(f"Error processing preproc_config for display: {e}")
                else:
                    display_text = str(item_data)
                
                # ---- ADDING DIAGNOSTIC LOGGING ----
                if db_key == "detected_text":
                    logging.info(f"[POPULATE_TABLE_DIAGNOSTIC] Row {row_idx}, Column '{display_header}', Retrieved detected_text: '{str(item_data)[:100]}...'")
                # ---- END DIAGNOSTIC LOGGING ----

                table_item = QTableWidgetItem(display_text)

                if db_key == "image_blob" and item_data is not None:
                    try:
                        q_image = QImage.fromData(item_data) # item_data is bytes from BLOB
                        if not q_image.isNull():
                            pixmap = QPixmap.fromImage(q_image)
                            # Scale pixmap to fit cell better, e.g., keeping aspect ratio with a fixed height
                            # This scaling should ideally happen before display or by using a delegate
                            # For simplicity, we can scale it here if needed, or rely on cell size
                            # scaled_pixmap = pixmap.scaledToHeight(90, Qt.TransformationMode.SmoothTransformation)
                            # table_item.setData(Qt.ItemDataRole.DecorationRole, scaled_pixmap)
                            table_item.setData(Qt.ItemDataRole.DecorationRole, pixmap) # Show original thumbnail size
                            table_item.setText("") # Clear any text if image is shown
                        else:
                            table_item.setText("[Gagal Muat]") # Failed to load image
                    except Exception as e:
                        print(f"Error loading image blob for display: {e}")
                        table_item.setText("[Kesalahan Gambar]")
                else:
                    # Set item flags: Editable or not
                    if display_header in self.EDITABLE_COLUMNS:
                        table_item.setFlags(table_item.flags() | Qt.ItemFlag.ItemIsEditable)
                    else:
                        table_item.setFlags(table_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    
                    # Specific alignment for ID column
                    if db_key == "id":
                        table_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                self.table_widget.setItem(row_idx, col_idx, table_item)
        
        self.table_widget.resizeColumnsToContents()
        # Special handling for image column width
        try:
            preview_col_idx = list(self.COLUMN_MAPPING.keys()).index("Pratinjau")
            self.table_widget.setColumnWidth(preview_col_idx, 160) # Set preview column width (adjust as needed)
        except ValueError:
            pass # Pratinjau column not found

        self._hide_columns() # Hide specified columns after resizing
        # Ensure last section stretch is on, especially if columns were hidden/shown
        if self.table_widget.columnCount() > 0:
             # Find last visible column to stretch
            last_visible_column = self.table_widget.columnCount() -1
            while last_visible_column >= 0 and self.table_widget.isColumnHidden(last_visible_column):
                last_visible_column -= 1
            
            # Iterate through all columns. Unset stretch from all but the last visible one.
            for i in range(self.table_widget.columnCount()):
                if i == last_visible_column and last_visible_column != -1:
                    self.table_widget.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
                else:
                    # Set to interactive for other columns, or whatever default you prefer
                    self.table_widget.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)

        self.status_label.setText(f"{len(results)} data dimuat.") # {len(results)} records loaded.
        self.table_widget.blockSignals(False) # Unblock signals after population

    # OOP: Encapsulation (Enkapsulasi) - Metode slot untuk menangani error pengambilan data.
    def handle_fetch_error(self, error_msg):
        """Shows an error message if fetching fails."""
        QMessageBox.critical(self, "Kesalahan Pengambilan Database", error_msg) # Database Fetch Error
        self.status_label.setText("Kesalahan mengambil riwayat.") # Error fetching history.

    # OOP: Encapsulation (Enkapsulasi) - Metode slot saat worker selesai.
    def fetch_finished(self):
        """Called when the fetch worker finishes."""
        self.refresh_button.setEnabled(True)
        # self.fetch_worker = None # This can cause issues if accessed right after, signal connection handles it
        print("DB fetch thread finished.")

    def handle_item_changed(self, item: QTableWidgetItem):
        """Handles changes to table items and updates the database."""
        if not item:  # Should not happen
            return

        row = item.row()
        column_index = item.column()
        column_header = self.table_widget.horizontalHeaderItem(column_index).text()

        # If the column is not designated as editable, do nothing.
        # The item flags should prevent editing, but this is an extra check.
        if column_header not in self.EDITABLE_COLUMNS:
            return

        # Get the record ID from the "ID" column
        id_column_idx = list(self.COLUMN_MAPPING.keys()).index("ID")
        id_item = self.table_widget.item(row, id_column_idx)
        if not id_item:
            QMessageBox.warning(self, "Kesalahan Internal", f"Tidak dapat menemukan ID untuk baris {row}.")
            return
        
        try:
            record_id = int(id_item.text())
            new_value_str = item.text()
            db_field_name = self.COLUMN_MAPPING[column_header]

            # Basic validation for numeric columns (PSM, OEM)
            if db_field_name in self.NUMERIC_COLUMNS:
                try:
                    new_value = int(new_value_str) # Attempt to convert to int
                except ValueError:
                    QMessageBox.warning(self, "Input Tidak Valid", f"Kolom '{column_header}' memerlukan angka.")
                    # To revert, we need the original value. For now, we block signals and setText.
                    self.table_widget.blockSignals(True)
                    # This is tricky because we don't have the "original" value easily.
                    # A full revert would require reloading the item or storing original values.
                    # For now, let's just inform and not update. A proper way is to use a QItemDelegate.
                    # Or, refetch the row:
                    # self.load_history() # This reloads everything, not ideal.
                    # For now, leave the invalid text, DB update will be skipped.
                    self.table_widget.blockSignals(False)
                    return # Stop processing if validation fails

            else:
                new_value = new_value_str # For text fields

            print(f"Attempting to update DB: ID={record_id}, Field='{db_field_name}', New Value='{new_value}'")
            
            # Temporarily disable itemChanged signal to prevent recursion if setText is called
            self.table_widget.blockSignals(True)

            success, message = update_ocr_record_field(record_id, db_field_name, new_value)

            if success:
                self.status_label.setText(f"Data '{db_field_name}' untuk ID {record_id} berhasil diperbarui.")
                # If the database formats/changes the value, you might want to update the item text here
                # item.setText(str(updated_value_from_db)) 
            else:
                QMessageBox.warning(self, "Kesalahan Pembaruan", f"Gagal memperbarui data di DB: {message}")
                # Attempt to revert UI:
                # This is complex without storing original value. A simple approach is to reload.
                # For now, the UI might be out of sync if DB update fails.
                # Consider reloading the specific row or item if possible.

        except ValueError as ve: # Should be caught by specific int conversion above
            QMessageBox.warning(self, "Input Tidak Valid", f"Nilai tidak valid untuk kolom {column_header}: {ve}")
        except Exception as e:
            QMessageBox.critical(self, "Kesalahan", f"Terjadi kesalahan tak terduga saat memperbarui: {e}")
            traceback.print_exc()
        finally:
            self.table_widget.blockSignals(False) # Always re-enable signals

    # OOP: Encapsulation (Enkapsulasi) - Metode helper internal (diawali _).
    def _hide_columns(self):
        """Hides columns specified in HIDDEN_COLUMNS."""
        column_names = list(self.COLUMN_MAPPING.keys())
        for i, header in enumerate(column_names):
            if header in self.HIDDEN_COLUMNS:
                self.table_widget.setColumnHidden(i, True)
            else:
                self.table_widget.setColumnHidden(i, False) # Ensure others are visible

    # OOP: Polymorphism (Polimorfisme) - Override metode closeEvent dari QDialog.
    def closeEvent(self, event):
        """Ensure worker thread is stopped if window is closed."""
        if self.fetch_worker and self.fetch_worker.isRunning():
            print("Terminating fetch worker...")
            self.fetch_worker.terminate()
            self.fetch_worker.wait()
        super().closeEvent(event) 
