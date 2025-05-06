import sys
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, 
    QPushButton, QAbstractItemView, QHeaderView, QMessageBox, QLabel, QMenu
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction
import traceback
import datetime
import json # For parsing preproc_config if needed for display

# Import the fetch function - db_operations.py now has fetch_all_results that doesn't fetch confidence
from .db_operations import fetch_all_results, delete_result_by_id 

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
        "Nama Berkas": "filename", # Filename
        "Bahasa": "language", # Language
        "PSM": "psm",
        "OEM": "oem",
        "Teks Terdeteksi": "detected_text", # Detected Text
        # "Image Path": "image_path", # Usually too long for direct display
        "Pra-pemrosesan": "preproc_config", # Preprocessing
        "Direktori Tessdata": "tessdata_dir" # Tessdata Dir
    }
    
    # OOP: Encapsulation (Enkapsulasi) - Define which columns to initially hide for brevity
    HIDDEN_COLUMNS = ["Teks Terdeteksi", "Direktori Tessdata", "Pra-pemrosesan"]

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
        self.table_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers) # Read-only
        self.table_widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_widget.setAlternatingRowColors(True)
        self.table_widget.verticalHeader().setVisible(False) # Hide row numbers
        # Resize columns to content initially, allow interactive resize
        self.table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        # Stretch last column (Processed At)
        self.table_widget.horizontalHeader().setStretchLastSection(True)

        # Context menu for deleting rows
        self.table_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_widget.customContextMenuRequested.connect(self.show_table_context_menu)

        layout.addWidget(self.table_widget)

        # --- Initial Load --- #
        self.load_history()
        self._hide_columns()

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
                elif db_key == "Pra-pemrosesan": # Key for preprocessing
                    try:
                        if isinstance(item_data, str):
                            data_dict = json.loads(item_data)
                        elif isinstance(item_data, dict):
                            data_dict = item_data
                        else:
                            data_dict = None
                        
                        if data_dict:
                            # Translate keys in preproc_config for display
                            translated_preproc = []
                            if data_dict.get('apply_deskew'): translated_preproc.append("Koreksi Kemiringan")
                            if data_dict.get('apply_clahe'): translated_preproc.append("CLAHE")
                            if data_dict.get('apply_spellcheck'): translated_preproc.append("Periksa Ejaan")
                            blur = data_dict.get('blur_type', 'None')
                            if blur != 'None': translated_preproc.append(f"Blur: {blur}")
                            display_text = ", ".join(translated_preproc) if translated_preproc else "Tidak ada"
                        else:
                            display_text = str(item_data)
                    except (json.JSONDecodeError, TypeError):
                        display_text = str(item_data)
                else:
                    display_text = str(item_data)
                
                item = QTableWidgetItem(display_text)
                if db_key == "id": item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table_widget.setItem(row_idx, col_idx, item)
        
        self.table_widget.resizeColumnsToContents() # Adjust columns after populating
        self._hide_columns() # Re-apply hidden columns after resizing
        self.status_label.setText(f"Berhasil memuat {len(results)} data.") # Loaded {len(results)} results.

    # OOP: Encapsulation (Enkapsulasi) - Metode slot untuk menangani error.
    def handle_fetch_error(self, error_msg):
        """Shows an error message if fetching fails."""
        QMessageBox.critical(self, "Kesalahan Pengambilan Database", error_msg) # Database Fetch Error
        self.status_label.setText("Kesalahan mengambil riwayat.") # Error fetching history.

    # OOP: Encapsulation (Enkapsulasi) - Metode slot saat worker selesai.
    def fetch_finished(self):
        """Called when the fetch worker finishes."""
        self.refresh_button.setEnabled(True)
        self.fetch_worker = None # Clear worker reference
        print("DB fetch thread finished.")
        
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