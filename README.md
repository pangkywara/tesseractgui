# Aplikasi GUI OCR Tesseract

## Deskripsi

Aplikasi desktop ini menyediakan antarmuka pengguna grafis (GUI) untuk melakukan Optical Character Recognition (OCR) pada gambar menggunakan mesin Tesseract. Aplikasi ini dibangun dengan Python dan PySide6.

## Fitur Utama

*   **Pemilihan Gambar:** Memilih berkas gambar (PNG, JPG, BMP, TIFF) dari sistem.
*   **Pratinjau Gambar:** Menampilkan pratinjau gambar yang dipilih.
*   **Eksekusi OCR:** Menjalankan proses OCR pada gambar yang dipilih di latar belakang (background thread) untuk menjaga responsivitas GUI.
*   **Konfigurasi OCR:** Mengatur parameter OCR melalui dialog Pengaturan Lanjutan:
    *   Bahasa Tesseract (mis., `eng`, `ind`, `eng+ind`).
    *   Direktori Tessdata (opsional).
    *   Mode Segmentasi Halaman (PSM).
    *   Mode Mesin OCR (OEM).
    *   Opsi Pra-pemrosesan Gambar (Koreksi Kemiringan, CLAHE, Pemeriksaan Ejaan).
*   **Tampilan Hasil:** Menampilkan teks hasil ekstraksi OCR.
*   **Penyimpanan Riwayat:** Menyimpan hasil OCR (nama berkas, teks, pengaturan yang digunakan, waktu) ke dalam basis data SQLite (`ocr_history.db`).
*   **Penampil Riwayat:** Menampilkan, menyegarkan, dan menghapus (baris per baris atau semua) data riwayat OCR.

## Teknologi

*   Python 3
*   PySide6 (untuk GUI)
*   OpenCV-Python (untuk pra-pemrosesan gambar)
*   Pytesseract (wrapper untuk Tesseract OCR engine)
*   SQLite (untuk basis data riwayat)
*   Pillow (dependency Pytesseract)
*   Pyspellchecker (untuk pemeriksaan ejaan opsional)

## Cara Menjalankan

1.  **Pastikan Tesseract OCR Engine Terinstal:** Aplikasi ini membutuhkan Tesseract versi 4 atau lebih baru terinstal di sistem Anda. Path ke `tesseract.exe` saat ini di-hardcode dalam `ocr_processing.py`.
2.  **Setup Lingkungan Virtual (Virtual Environment):**
    *   Buka terminal di direktori `gui_app`.
    *   Buat lingkungan virtual: `python -m venv env`
    *   Aktifkan lingkungan virtual:
        *   Windows: `.\env\Scripts\activate`
        *   macOS/Linux: `source env/bin/activate`
    *   Instal dependensi: `pip install -r requirements.txt`
3.  **Jalankan Aplikasi:**
    *   **Penting:** Jalankan dari direktori **di atas** `gui_app` (yaitu, direktori utama proyek `Nama folder Anda`).
    *   Di terminal (dengan lingkungan virtual aktif), jalankan perintah: `python -m gui_app.main_pyside`

4.  **(Opsional) Hapus Basis Data Lama:** Jika Anda mengubah struktur tabel basis data (seperti yang dilakukan saat pengembangan), hapus berkas `gui_app/ocr_history.db` agar aplikasi dapat membuatnya kembali dengan skema baru saat dijalankan. 
