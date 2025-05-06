import sys
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QTextEdit, QFileDialog, QGroupBox, QCheckBox, 
    QRadioButton, QComboBox, QLineEdit, QStatusBar, QMessageBox, QGridLayout,
    QScrollArea, QSizePolicy, QDialog, QFormLayout, QDialogButtonBox, QTabWidget
)
from PySide6.QtGui import QPixmap, QAction, QIcon, QImage, QPainter, QPen, QColor, QPalette
from PySide6.QtCore import Qt, QThread, Signal, QRectF, QPoint, QSettings

# Import CV2 for image conversion if needed
import cv2
import numpy as np
import sqlite3 # Added for exception handling
import pytesseract # Imported for TesseractNotFoundError

# Placeholder for imports from your existing modules
from .ocr_processing import perform_ocr, OcrResult
# Import the DB saving function
from .db_operations import (
    save_ocr_result_to_db,  # Changed from save_ocr_result_to_mysql
    get_db_connection,
    clear_all_ocr_results # Added clear_all_ocr_results
)
# Import the History Window
from .history_window import HistoryWindow

# OOP: Abstraksi - Menyediakan konstanta terdefinisi untuk opsi yang kompleks,
# menyembunyikan nilai integer spesifik Tesseract dari pengguna langsung.
PREPROCESSING_OPTIONS = {
    "apply_deskew": "Terapkan Koreksi Kemiringan (Deskew)",
    "apply_clahe": "Terapkan CLAHE (Peningkatan Kontras)",
    "apply_spellcheck": "Terapkan Pemeriksaan Ejaan (hanya Eng)",
    # Note: Blur is handled via a string option, not a boolean here
}

# --- Define Tesseract PSM Options Here --- #
PSM_OPTIONS = {
    "0: Deteksi orientasi dan skrip (OSD) saja.": 0,
    "1: Segmentasi halaman otomatis dengan OSD.": 1,
    "2: Segmentasi halaman otomatis, tanpa OSD atau OCR.": 2,
    "3: Segmentasi halaman sepenuhnya otomatis, tanpa OSD. (Default)": 3,
    "4: Asumsikan satu kolom teks dengan berbagai ukuran.": 4,
    "5: Asumsikan satu blok teks vertikal yang seragam.": 5,
    "6: Asumsikan satu blok teks yang seragam.": 6,
    "7: Perlakukan gambar sebagai satu baris teks.": 7,
    "8: Perlakukan gambar sebagai satu kata.": 8,
    "9: Perlakukan gambar sebagai satu kata dalam lingkaran.": 9,
    "10: Perlakukan gambar sebagai satu karakter.": 10,
    "11: Teks jarang. Temukan teks sebanyak mungkin tanpa urutan tertentu.": 11,
    "12: Teks jarang dengan OSD.": 12,
    "13: Baris mentah. Perlakukan gambar sebagai satu baris teks, melewati peretasan spesifik Tesseract.": 13,
}

# OOP: Inheritance (Pewarisan) - OcrWorker mewarisi fungsionalitas dari QThread.
# OOP: Abstraksi - Menyembunyikan detail manajemen thread dari MainWindow.
class OcrWorker(QThread):
    """Worker thread for running OCR to avoid blocking the GUI."""
    # Signals to communicate results or errors back to the main thread
    result_ready = Signal(OcrResult) # Emits OcrResult (which no longer has .words)
    error_occurred = Signal(str)
    image_processed = Signal(np.ndarray) # For processed image preview if ever re-enabled
    
    # OOP: Encapsulation (Enkapsulasi) - Menyimpan data path gambar dan opsi.
    def __init__(self, image_path: str, options: dict):
        super().__init__()
        self.image_path = image_path # image_path is also in options, kept for clarity
        self.options = options 

    # OOP: Polymorphism (Polimorfisme) - Meng-override metode run() dari QThread.
    def run(self):
        """The function executed in the separate thread."""
        try:
            # Replace with actual call to your OCR logic
            print(f"Worker: Starting OCR for {self.image_path} with options: {self.options}")
            # Pass the options dictionary directly using **
            ocr_result_obj, processed_img_array = perform_ocr(**self.options)

            # --- Dummy Example Data --- # REMOVED
            # processed_image_np = None 
            # class DummyWord:
            #     def __init__(self, t, l, tp, w, h): self.text, self.left, self.top, self.width, self.height = t, l, tp, w, h
            # class DummyResult:
            #      def __init__(self): self.full_text = "Dummy OCR Result Text"; self.words = [DummyWord('Dummy', 10, 10, 50, 20), DummyWord('Text', 70, 10, 40, 20)]
            # ocr_result = DummyResult()
            # --------------------------- # REMOVED

            print("Worker: OCR finished.")
            # Emit signals with the actual results
            if processed_img_array is not None:
                self.image_processed.emit(processed_img_array)
            if ocr_result_obj:
                self.result_ready.emit(ocr_result_obj)
            else:
                self.error_occurred.emit("Proses OCR tidak menghasilkan objek hasil.")
                
        except pytesseract.TesseractNotFoundError: # Tangani error spesifik ini
            self.error_occurred.emit("Tesseract tidak ditemukan. Pastikan sudah terinstal dan ada di PATH sistem Anda.")
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error_occurred.emit(f"Kesalahan saat OCR: {type(e).__name__}: {e}")


# OOP: Inheritance (Pewarisan) - DbSaveWorker mewarisi fungsionalitas dari QThread.
# OOP: Abstraksi - Menyembunyikan detail penyimpanan DB asinkron dari MainWindow.
class DbSaveWorker(QThread):
    """Worker thread for saving OCR results to the database."""

    finished = Signal()
    error = Signal(str)
    # Removed mysql_config parameter
    def __init__(self, ocr_result: OcrResult, ocr_options: dict, parent=None):
        super().__init__(parent)
        self.ocr_result = ocr_result
        self.ocr_options = ocr_options
        # self.mysql_config = mysql_config # Removed


    def run(self):
        """Save the OCR result to the database."""
        try:
            # Pass only the result object
            preproc_config_dict = {
                'apply_deskew': self.ocr_options.get('apply_deskew', False),
                'apply_clahe': self.ocr_options.get('apply_clahe', False),
                'blur_type': self.ocr_options.get('blur_type', 'None'),
                'apply_spellcheck': self.ocr_options.get('apply_spellcheck', False)
            }

            result_data_dict = {
                'filename': os.path.basename(self.ocr_options.get('image_path', 'Tidak Diketahui')),
                'language': self.ocr_options.get('lang', 'eng'),
                'psm': self.ocr_options.get('psm', 3),
                'oem': self.ocr_options.get('oem', 3),
                'detected_text': self.ocr_result.full_text,
                'image_path': self.ocr_options.get('image_path', 'Tidak Diketahui'),
                'preproc_config': preproc_config_dict, # This will be JSON serialized by db_operations
                'tessdata_dir': self.ocr_options.get('tessdata_dir')
                # 'confidence' and 'word_boxes' are no longer included
            }
            save_ocr_result_to_db(result_data_dict)
            self.finished.emit()
        except sqlite3.Error as e: # Changed from DatabaseConnectionError
            self.error.emit(f"Kesalahan DB SQLite: {e}")
        except Exception as e:
            self.error.emit(f"Gagal menyiapkan/menyimpan hasil ke DB: {e}")


# OOP: Inheritance (Pewarisan) - SettingsDialog mewarisi dari QDialog.
# OOP: Encapsulation (Enkapsulasi) - Mengelola widget dan logika untuk dialog pengaturan.
class SettingsDialog(QDialog):
    """Dialog for configuring application settings."""
    def __init__(self, settings: QSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Pengaturan")
        self.setMinimumWidth(500) # Lebar disesuaikan untuk teks Bahasa Indonesia

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        tab_widget = QTabWidget()
        main_layout.addWidget(tab_widget)

        # --- OCR Options Tab (Now the first tab if Tesseract tab is removed) ---
        ocr_tab = QWidget()
        # Give ocr_layout a name to be used for adding widgets
        ocr_options_layout = QGridLayout(ocr_tab) # Changed variable name for clarity
        tab_widget.addTab(ocr_tab, "Opsi OCR")

        # Tessdata Directory (Moved to OCR Options or its own tab if preferred)
        tessdata_dir_layout = QHBoxLayout()
        self.tessdata_dir_label = QLabel("Direktori Tessdata:")
        self.tessdata_dir_edit = QLineEdit(
            self.settings.value("ocr/tessdata_dir", "")
        )
        self.tessdata_dir_edit.setPlaceholderText("(Opsional) Path ke direktori tessdata")
        self.tessdata_dir_browse_button = QPushButton("Telusuri...")
        self.tessdata_dir_browse_button.clicked.connect(self.browse_tessdata_dir)
        tessdata_dir_layout.addWidget(self.tessdata_dir_label)
        tessdata_dir_layout.addWidget(self.tessdata_dir_edit)
        tessdata_dir_layout.addWidget(self.tessdata_dir_browse_button)
        ocr_options_layout.addLayout(tessdata_dir_layout, 0, 0, 1, 2) # Span 2 columns

        # Language
        self.language_label = QLabel("Bahasa OCR:")
        self.language_edit = QLineEdit(self.settings.value("ocr/language", "eng"))
        self.language_edit.setToolTip("Kode bahasa Tesseract, mis., 'eng' atau 'ind+eng'")
        ocr_options_layout.addWidget(self.language_label, 1, 0)
        ocr_options_layout.addWidget(self.language_edit, 1, 1)

        # PSM
        self.psm_label = QLabel("Mode Segmentasi Halaman (PSM):")
        self.psm_combobox = QComboBox()
        for desc, value in PSM_OPTIONS.items():
            self.psm_combobox.addItem(f"{value}: {desc}", value)
        current_psm = self.settings.value("ocr/psm", 3, type=int)
        psm_index = self.psm_combobox.findData(current_psm)
        if psm_index != -1:
            self.psm_combobox.setCurrentIndex(psm_index)
        ocr_options_layout.addWidget(self.psm_label, 2, 0)
        ocr_options_layout.addWidget(self.psm_combobox, 2, 1)

        # OEM
        self.oem_label = QLabel("Mode Mesin OCR (OEM):")
        self.oem_combobox = QComboBox()
        oem_options = {
            "0: Hanya Mesin Legacy.": 0,
            "1: Hanya Mesin Neural nets LSTM.": 1,
            "2: Mesin Legacy + LSTM.": 2,
            "3: Default, berdasarkan ketersediaan.": 3,
        }
        for desc, value in oem_options.items():
            self.oem_combobox.addItem(f"{value}: {desc}", value)
        current_oem = self.settings.value("ocr/oem", 3, type=int)
        oem_index = self.oem_combobox.findData(current_oem)
        if oem_index != -1:
            self.oem_combobox.setCurrentIndex(oem_index)
        ocr_options_layout.addWidget(self.oem_label, 3, 0)
        ocr_options_layout.addWidget(self.oem_combobox, 3, 1)
        
        ocr_options_layout.setRowStretch(4, 1) # Add stretch at the end of OCR options tab

        # --- Preprocessing Tab ---
        preprocessing_tab = QWidget()
        preprocessing_layout = QGridLayout(preprocessing_tab)
        tab_widget.addTab(preprocessing_tab, "Pra-pemrosesan")
        self.preprocessing_checkboxes = {}
        row = 0
        col = 0
        self.settings.beginGroup("preprocessing")
        for name, description in PREPROCESSING_OPTIONS.items():
            checkbox = QCheckBox(description)
            setting_value = self.settings.value(name, False)
            if isinstance(setting_value, str):
                is_checked = setting_value.lower() == 'true'
            else:
                is_checked = bool(setting_value)
            checkbox.setChecked(is_checked)
            self.preprocessing_checkboxes[name] = checkbox
            preprocessing_layout.addWidget(checkbox, row, col)
            col += 1
            if col > 1:
                col = 0
                row += 1
        self.settings.endGroup()
        preprocessing_layout.setRowStretch(row + 1, 1) # Add stretch

        # --- Buttons (OK/Cancel) ---
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button = QPushButton("Batal")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        main_layout.addLayout(button_layout)

    # OOP: Encapsulation (Enkapsulasi) - Metode privat (konvensi _) jika ada,
    # atau metode publik yang mengelola state internal dialog.
    def browse_tessdata_dir(self):
        dir_name = QFileDialog.getExistingDirectory(self, "Pilih Direktori Tessdata", "")
        if dir_name:
            self.tessdata_dir_edit.setText(dir_name)

    # OOP: Polymorphism (Polimorfisme) - Meng-override metode accept() dari QDialog.
    def accept(self):
        # Removed saving Tesseract path
        # Save OCR options
        self.settings.setValue("ocr/language", self.language_edit.text())
        self.settings.setValue("ocr/tessdata_dir", self.tessdata_dir_edit.text())
        self.settings.setValue("ocr/psm", self.psm_combobox.currentData())
        self.settings.setValue("ocr/oem", self.oem_combobox.currentData())

        # Save Preprocessing options
        self.settings.beginGroup("preprocessing")
        for name, checkbox in self.preprocessing_checkboxes.items():
            self.settings.setValue(name, checkbox.isChecked())
        self.settings.endGroup()
        super().accept()


# OOP: Inheritance (Pewarisan) - MainWindow mewarisi dari QMainWindow.
# OOP: Encapsulation (Enkapsulasi) - Mengelola state utama aplikasi (path gambar, hasil OCR, worker),
# dan semua widget serta logika interaksi UI.
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Aplikasi OCR Tesseract (PySide6)") # Judul Window Utama
        self.setGeometry(100, 100, 900, 750)
        self.set_dark_palette()
        
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Inisialisasi...") # Pesan status awal

        self.settings = QSettings("PBOTesseract", "GUIApp")
        self.load_initial_settings() # This will no longer load tesseract_path
        
        self.current_image_path: str | None = None
        self.current_ocr_result: OcrResult | None = None
        self.ocr_worker: OcrWorker | None = None
        self.db_save_worker: DbSaveWorker | None = None
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        self._create_menus()
        self.status_bar.showMessage("Siap") # Pesan status setelah inisialisasi
        
        top_controls_widget = QWidget()
        top_controls_layout = QHBoxLayout(top_controls_widget)
        top_controls_layout.setSpacing(15)
        main_layout.addWidget(top_controls_widget, 0)
        
        self.select_button = QPushButton("Pilih Gambar"); self.select_button.clicked.connect(self.select_image_file)
        self.file_label = QLabel("Tidak ada gambar dipilih");
        top_controls_layout.addWidget(self.select_button)
        top_controls_layout.addWidget(self.file_label, 1)
        
        lang_group = QGroupBox("Bahasa Default") # Judul grup bahasa
        lang_layout = QHBoxLayout(lang_group)
        self.lang_eng_radio = QRadioButton("Inggris (eng)"); self.lang_eng_radio.setChecked(self.settings.value("ocr/language", "eng") == "eng"); self.lang_eng_radio.toggled.connect(lambda: self.update_language_setting('eng'))
        self.lang_ind_radio = QRadioButton("Indonesia (ind)"); self.lang_ind_radio.setChecked(self.settings.value("ocr/language", "eng") == "ind"); self.lang_ind_radio.toggled.connect(lambda: self.update_language_setting('ind'))
        lang_layout.addWidget(self.lang_eng_radio); lang_layout.addWidget(self.lang_ind_radio)
        top_controls_layout.addWidget(lang_group)

        self.settings_button = QPushButton("Pengaturan Lanjutan...")
        self.settings_button.clicked.connect(self.open_settings_dialog)
        top_controls_layout.addWidget(self.settings_button)
        
        top_controls_layout.addStretch(1)
        
        self.ocr_button = QPushButton("Lakukan OCR"); self.ocr_button.setEnabled(False); self.ocr_button.setMinimumHeight(40); self.ocr_button.clicked.connect(self.start_ocr)
        main_layout.addWidget(self.ocr_button, 0, Qt.AlignmentFlag.AlignCenter)

        bottom_text_group = QGroupBox("Hasil OCR") # Judul grup hasil
        bottom_text_layout = QVBoxLayout(bottom_text_group)
        bottom_text_layout.addWidget(QLabel("Teks Hasil Ekstraksi:"))
        self.full_text_edit = QTextEdit(); self.full_text_edit.setReadOnly(True); self.full_text_edit.setMinimumHeight(100); bottom_text_layout.addWidget(self.full_text_edit)

        self.image_scroll_area = QScrollArea(); self.image_scroll_area.setBackgroundRole(QPalette.ColorRole.Dark); self.image_scroll_area.setWidgetResizable(True)
        self.image_display_label = QLabel("Pilih gambar untuk pratinjau") 
        self.image_display_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_display_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.image_display_label.setMinimumSize(300, 200)
        self.image_scroll_area.setWidget(self.image_display_label)
        main_layout.addWidget(self.image_scroll_area, 1)

        main_layout.addWidget(bottom_text_group)

    # OOP: Encapsulation (Enkapsulasi) - Metode helper internal (diawali _).
    def _create_menus(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&Berkas");
        select_action = QAction("Pilih &Gambar...", self); select_action.triggered.connect(self.select_image_file); file_menu.addAction(select_action)
        file_menu.addSeparator()
        settings_action = QAction("&Pengaturan...", self); settings_action.triggered.connect(self.open_settings_dialog); file_menu.addAction(settings_action)
        file_menu.addSeparator()
        exit_action = QAction("&Keluar", self); exit_action.triggered.connect(self.close); file_menu.addAction(exit_action)
        
        view_menu = menu_bar.addMenu("&Tampilan");
        history_action = QAction("Lihat &Riwayat OCR...", self); history_action.triggered.connect(self.show_history_window); view_menu.addAction(history_action)
        view_menu.addSeparator()
        clear_history_action = QAction("Hapus Semua &Riwayat...", self) # Aksi baru
        clear_history_action.triggered.connect(self.confirm_clear_all_history)
        view_menu.addAction(clear_history_action)
        
    def update_language_setting(self, lang_code):
        self.settings.setValue("ocr/language", lang_code)
        self.status_bar.showMessage(f"Bahasa default diatur ke: {lang_code}", 2000)
        # Update radio button states if not already correct (though toggled should handle this)
        if lang_code == 'eng':
            self.lang_eng_radio.setChecked(True)
        elif lang_code == 'ind':
            self.lang_ind_radio.setChecked(True)

    def open_settings_dialog(self):
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec():
            self.load_initial_settings() 
            self.status_bar.showMessage("Pengaturan diperbarui.", 3000)
            # No Tesseract path validation needed here anymore

    def select_image_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Pilih Berkas Gambar", "", "Berkas Gambar (*.png *.jpg *.jpeg *.bmp *.tiff)")
        if file_path:
            self.current_image_path = file_path; 
            self.file_label.setText(f"<b>Terpilih:</b> {os.path.basename(file_path)}") 
            self.status_bar.showMessage(f"Dipilih: {file_path}"); self.ocr_button.setEnabled(True)
            self.full_text_edit.clear()
            self.current_ocr_result = None
            
            try:
                pixmap = QPixmap(file_path)
                if pixmap.isNull():
                    self.image_display_label.setText("Tidak dapat memuat pratinjau gambar.")
                    QMessageBox.warning(self, "Kesalahan Muat Gambar", f"Tidak dapat memuat berkas gambar:\n{file_path}")
                else:
                    scaled_pixmap = pixmap.scaled(
                        self.image_scroll_area.viewport().size(), 
                        Qt.AspectRatioMode.KeepAspectRatio, 
                        Qt.TransformationMode.SmoothTransformation
                    )
                    self.image_display_label.setPixmap(scaled_pixmap)
            except Exception as e:
                self.image_display_label.setText(f"Kesalahan memuat pratinjau: {e}")
                QMessageBox.critical(self, "Kesalahan Pratinjau", f"Kesalahan memuat pratinjau gambar:\n{e}")

    # OOP: Encapsulation (Enkapsulasi) - Metode mengelola state dan interaksi.
    def start_ocr(self):
        if not self.current_image_path:
            QMessageBox.warning(self, "Peringatan", "Silakan pilih gambar terlebih dahulu."); return
        
        tessdata_dir = self.settings.value("ocr/tessdata_dir")
        if tessdata_dir and not os.path.isdir(tessdata_dir):
             QMessageBox.warning(self, "Peringatan", f"Direktori Tessdata pada pengaturan tidak valid: {tessdata_dir}\nMenggunakan default.")
             self.settings.setValue("ocr/tessdata_dir", "")
             tessdata_dir = None 

        ocr_options = {
            "image_path": self.current_image_path,
            "lang": self.settings.value("ocr/language", "eng"),
            "psm": self.settings.value("ocr/psm", 3, type=int),
            "oem": self.settings.value("ocr/oem", 3, type=int),
            "tessdata_dir": tessdata_dir, 
            "apply_deskew": self.settings.value("preprocessing/apply_deskew", True, type=bool),
            "apply_clahe": self.settings.value("preprocessing/apply_clahe", True, type=bool),
            "blur_type": self.settings.value("preprocessing/blur_type", "Gaussian"),
            "apply_spellcheck": self.settings.value("preprocessing/apply_spellcheck", True, type=bool)
        }
        
        self.status_bar.showMessage(f"Memulai OCR...")
        self.select_button.setEnabled(False); self.settings_button.setEnabled(False); self.ocr_button.setEnabled(False)
        
        self.ocr_worker = OcrWorker(self.current_image_path, ocr_options)
        self.ocr_worker.result_ready.connect(self.handle_ocr_result)
        self.ocr_worker.error_occurred.connect(self.handle_ocr_error)
        # self.ocr_worker.image_processed.connect(self.handle_processed_image) # DISCONNECTED for original preview only
        self.ocr_worker.finished.connect(self.ocr_finished)
        self.ocr_worker.start()

    # OOP: Encapsulation (Enkapsulasi) - Metode slot yang bereaksi terhadap sinyal worker.
    def handle_ocr_result(self, result: OcrResult):
        self.current_ocr_result = result
        self.full_text_edit.setPlainText(getattr(result, 'full_text', 'Teks tidak ditemukan'))
        self.status_bar.showMessage("OCR results processed.")

        if self.current_ocr_result and self.current_ocr_result.full_text:
            self.status_bar.showMessage("OCR complete. Saving to SQLite...")
            self.db_save_worker = DbSaveWorker(self.current_ocr_result, self.ocr_worker.options)
            self.db_save_worker.finished.connect(self.handle_db_save_finished)
            self.db_save_worker.error.connect(self.handle_db_save_error)
            self.db_save_worker.finished.connect(self.db_save_worker.deleteLater)
            self.db_save_worker.error.connect(self.db_save_worker.deleteLater)
            self.db_save_worker.start()
        else:
            self.status_bar.showMessage("OCR complete. Nothing to save.")

    def handle_ocr_error(self, error_message):
        self.full_text_edit.setText(f"Error:\n{error_message}")
        self.status_bar.showMessage(f"OCR Error: {error_message}", 5000)
        # Re-enable buttons after error
        self.select_button.setEnabled(True); self.settings_button.setEnabled(True); self.ocr_button.setEnabled(True)

    def ocr_finished(self):
        self.select_button.setEnabled(True); self.settings_button.setEnabled(True); self.ocr_button.setEnabled(True)
        if self.ocr_worker:
            self.ocr_worker.deleteLater() # Schedule worker for deletion
            self.ocr_worker = None
        # Status message is handled by handle_ocr_result or handle_ocr_error

    def handle_db_save_finished(self):
        self.status_bar.showMessage("Result saved to SQLite successfully.", 3000)
        self.db_save_worker = None 

    def handle_db_save_error(self, error_message):
        QMessageBox.warning(self, "Database Save Error", error_message)
        self.status_bar.showMessage(f"Error saving result to SQLite: {error_message}", 5000)
        self.db_save_worker = None
        
    # OOP: Polymorphism (Polimorfisme) - Meng-override metode closeEvent() dari QWidget/QMainWindow.
    def closeEvent(self, event):
        reply = QMessageBox.question(self, 'Exit Confirmation', 
                                       "Apakah Anda yakin ingin keluar?", 
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                                       QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            if self.ocr_worker and self.ocr_worker.isRunning():
                self.ocr_worker.terminate(); self.ocr_worker.wait()
            if self.db_save_worker and self.db_save_worker.isRunning():
                 self.db_save_worker.terminate(); self.db_save_worker.wait()
            event.accept()
        else:
            event.ignore()

    def set_dark_palette(self):
        """Applies a standard dark palette to the application."""
        dark_palette = QPalette()
        # Base colors
        dark_palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.Base, QColor(42, 42, 42))
        dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(66, 66, 66))
        dark_palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        # Link colors
        dark_palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        # Highlight colors
        dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
        # Disabled colors
        dark_palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(127, 127, 127))
        dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(127, 127, 127))
        dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(127, 127, 127))
        dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(127, 127, 127))
        
        app = QApplication.instance() # Get the application instance
        if app:
             app.setPalette(dark_palette)
        else:
             print("Warning: No QApplication instance found to set palette.")

    def show_history_window(self):
        """Show the OCR history window."""
        try:
            self.history_win = HistoryWindow(parent=self)
            self.history_win.show()
        except sqlite3.Error as e:
             QMessageBox.critical(self, "Database Error", f"Could not connect to the history database (SQLite Error): {e}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open history window: {e}")
            import traceback
            traceback.print_exc()

    def load_initial_settings(self):
        # Removed self.tesseract_path loading
        self.psm = self.settings.value("ocr/psm", 3, type=int)
        self.language = self.settings.value("ocr/language", "eng")
        self.tessdata_dir = self.settings.value("ocr/tessdata_dir", "")
        self.oem = self.settings.value("ocr/oem", 3, type=int)

        self.preprocessing_settings = {}
        self.settings.beginGroup("preprocessing")
        for key in PREPROCESSING_OPTIONS:
            value = self.settings.value(key, False)
            if isinstance(value, str):
                self.preprocessing_settings[key] = value.lower() == 'true'
            else:
                self.preprocessing_settings[key] = bool(value)
            if key == 'adaptive_threshold': # This key is not in PREPROCESSING_OPTIONS
                pass # Keep adaptive threshold params if they were ever set, or remove this block
        self.settings.endGroup()

        # Removed Tesseract path validation from status bar
        # The status_bar.showMessage("Ready") in __init__ is now the default startup message.

    def confirm_clear_all_history(self):
        reply = QMessageBox.question(self, "Konfirmasi Hapus Riwayat",
                                     "Apakah Anda yakin ingin menghapus semua riwayat OCR? Tindakan ini tidak dapat diurungkan.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            if clear_all_ocr_results():
                self.status_bar.showMessage("Semua riwayat OCR berhasil dihapus.", 3000)
                QMessageBox.information(self, "Riwayat Dihapus", "Semua data riwayat OCR telah dihapus.")
                # Refresh history window if open? (More complex, for now just inform)
            else:
                self.status_bar.showMessage("Gagal menghapus riwayat OCR.", 3000)
                QMessageBox.warning(self, "Kesalahan", "Gagal menghapus riwayat OCR dari database.")


if __name__ == '__main__':
    import traceback
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec()) 