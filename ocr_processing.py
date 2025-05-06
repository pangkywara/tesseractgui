import pytesseract
from PIL import Image
import cv2
import numpy as np
import os
import math # Added for deskew calculation
from spellchecker import SpellChecker # Added import
import re # Added for splitting words
import pandas as pd # Import pandas for data handling
from pydantic import BaseModel # Import BaseModel
from typing import List, Dict, Any, Optional, Tuple # Ensure List, Tuple are imported

# --- Constants --- #
MIN_OCR_CONFIDENCE = 35 # Confidence threshold to filter weak detections
# Default noise reduction strength (adjust as needed)
DEFAULT_DENOISE_STRENGTH = 10
# Default kernel size for morphological operations
# MORPH_KERNEL_SIZE = (3,3) # Removed

# --- Pydantic Models for Structured Output ---
# WordData class removed as individual word details (boxes, per-word confidence) are not stored

# OOP: Encapsulation (Enkapsulasi) - Pydantic BaseModel digunakan untuk mengenkapsulasi
# struktur data hasil OCR, memastikan tipe data yang benar.
class OcrResult(BaseModel):
    # words: List[WordData] # Removed - individual word data no longer stored in this structure for DB
    full_text: str
    processed_image_width: int
    processed_image_height: int

# --- Tesseract Configuration --- #
# Hardcoding the Tesseract path as requested by the user.
# Make sure this path is correct for the system where the app will run.
pytesseract.pytesseract.tesseract_cmd = r'C:/Program Files/Tesseract-OCR/tesseract.exe'

# --- Image Deskewing Function ---
# OOP: Abstraksi - Fungsi ini menyembunyikan kompleksitas algoritma koreksi kemiringan.
def deskew_image(gray_image: np.ndarray) -> np.ndarray:
    """Estimates skew angle and rotates the grayscale image to correct it."""
    print("Attempting image deskewing...")
    try:
        # Invert the image (make text white, background black) for contour finding
        inverted = cv2.bitwise_not(gray_image)
        # Thresholding helps solidify text blocks
        _, thresh = cv2.threshold(inverted, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Find coordinates of all non-zero pixels (potential text)
        coords = np.column_stack(np.where(thresh > 0))

        if coords.size == 0:
            print("Deskewing: No contours found, skipping rotation.")
            return gray_image # Return original if no text found

        # Get the minimum area bounding rectangle for these points
        # rect is ((center_x, center_y), (width, height), angle)
        rect = cv2.minAreaRect(coords)
        angle = rect[-1]

        # Adjust angle: minAreaRect returns angles in [-90, 0).
        # We want the angle relative to the horizontal axis.
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle

        print(f"Deskewing: Estimated Angle = {angle:.2f} degrees")

        # Only rotate if the angle is significant (e.g., > 0.5 degrees)
        if abs(angle) > 0.5:
            (h, w) = gray_image.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)

            # Rotate the original grayscale image, filling background with white
            rotated = cv2.warpAffine(gray_image, M, (w, h),
                                     flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
                                     # borderValue=(255, 255, 255)) # White background

            print("Deskewing: Image rotated.")
            return rotated
        else:
            print("Deskewing: Angle too small, skipping rotation.")
            return gray_image

    except Exception as e:
        print(f"Error during deskewing: {e}. Returning original image.")
        # import traceback # Optional for detailed debugging
        # traceback.print_exc()
        return gray_image # Return original in case of error

# --- Text Post-processing Function ---
# OOP: Abstraksi - Fungsi ini menyembunyikan detail pemeriksaan dan koreksi ejaan.
def postprocess_text(text: str, lang: str) -> str:
    """Applies spell correction to the extracted text (currently optimized for English)."""
    if lang != 'eng':
        print(f"Skipping spell check: Not implemented/optimized for language '{lang}'.")
        return text

    print("Applying spell checking (English)...")
    try:
        spell = SpellChecker(language='en')

        # Split text into words, handling punctuation better
        words = re.findall(r'\b\w+\b', text.lower()) # Find word tokens, convert to lowercase
        if not words:
            return text # Return original if no words found

        # Find potentially misspelled words
        misspelled = spell.unknown(words)
        print(f"Found {len(misspelled)} potentially unknown words.")

        corrected_text = text
        for word in misspelled:
            # Get the one `most likely` answer
            correction = spell.correction(word)
            if correction and correction != word:
                # Basic replacement - might need refinement for case sensitivity or context
                # Using regex to replace whole words only, case-insensitive
                # This is a simple approach, might miscorrect proper nouns or technical terms
                print(f"Correcting '{word}' -> '{correction}'")
                # Use regex boundary \b to match whole words, ignore case
                corrected_text = re.sub(r'\b' + re.escape(word) + r'\b', correction, corrected_text, flags=re.IGNORECASE)

        return corrected_text
    except Exception as e:
        print(f"Error during spell checking: {e}. Returning original text.")
        return text

# --- Image Preprocessing Function ---
# OOP: Abstraksi - Fungsi ini menyembunyikan langkah-langkah pra-pemrosesan gambar.
def preprocess_image_for_ocr(
    image_path: str,
    apply_deskew: bool = True,
    apply_clahe: bool = True,
    # apply_denoise: bool = True, # New option - REMOVED
    # denoise_strength: int = DEFAULT_DENOISE_STRENGTH, # New option - REMOVED
    # apply_morph_open: bool = True, # New option - REMOVED
    blur_type: str = "Gaussian"
) -> np.ndarray:
    """Loads image, converts to grayscale, and applies selected preprocessing."""
    try:
        img = cv2.imread(image_path)
        if img is None: raise ValueError("Could not read image file.")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        current_image = gray

        # --- Denoising (Optional - Applied early on grayscale) ---
        # REMOVED Denoising block
        # if apply_denoise:
        #     print(f"Applying Non-Local Means Denoising (Strength: {denoise_strength})...")
        #     current_image = cv2.fastNlMeansDenoising(current_image, None, h=float(denoise_strength), templateWindowSize=7, searchWindowSize=21)
        # else:
        #     print("Skipping Denoising.")
        # ----------------------------------------------------------

        # --- Deskew (Optional) ---
        if apply_deskew: current_image = deskew_image(current_image)
        else: print("Skipping Deskew.")
        # -------------------------

        # --- CLAHE (Optional - Contrast Limited Adaptive Histogram Equalization) ---
        if apply_clahe:
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            current_image = clahe.apply(current_image)
            print("Applied CLAHE.")
        else: print("Skipping CLAHE.")
        # --------------------------------------------------------------------------

        # --- Blur (Optional - Applied before thresholding) ---
        if blur_type == "Gaussian":
            current_image = cv2.GaussianBlur(current_image, (5, 5), 0)
            print("Applied Gaussian Blur.")
        elif blur_type == "Median":
            current_image = cv2.medianBlur(current_image, 5)
            print("Applied Median Blur.")
        elif blur_type != "None":
             print(f"Warning: Unknown blur type '{blur_type}'. Skipping blur.")
        else:
             print("Skipping Blur.")
        # ---------------------------------------------------

        # --- Adaptive Thresholding (Key step for binarization) ---
        # Match backend parameters
        block_size = 11 # Backend uses 11
        C_value = 4     # Backend uses 4
        thresh_image = cv2.adaptiveThreshold(
            current_image,
            255, # Max value
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C, # Method
            cv2.THRESH_BINARY_INV, # Invert: Text becomes white, background black
            block_size, # Neighborhood size (must be odd)
            C_value 
        )
        print(f"Applied Gaussian Adaptive Thresholding (Block: {block_size}, C: {C_value}, INVERTED).")
        # ----------------------------------------------------

        # --- Morphological Opening (Optional - Remove noise post-thresholding) ---
        # REMOVED Morphological Opening block
        # if apply_morph_open:
        #     kernel = np.ones(MORPH_KERNEL_SIZE, np.uint8)
        #     opened_image = cv2.morphologyEx(thresh_image, cv2.MORPH_OPEN, kernel)
        #     print(f"Applied Morphological Opening (Kernel: {MORPH_KERNEL_SIZE}).")
        #     final_image = opened_image
        # else:
        #     print("Skipping Morphological Opening.")
        #     final_image = thresh_image # Use thresholded if not opening
        # --------------------------------------------------------------------------

        # Return the thresholded image directly, as the backend does
        return thresh_image

    except Exception as e:
        print(f"Error during image preprocessing: {e}")
        raise

# --- Actual OCR Logic ---
# OOP: Abstraksi - Fungsi utama yang menyembunyikan seluruh alur kerja OCR,
# mulai dari pra-pemrosesan hingga pemrosesan hasil Tesseract.
def perform_ocr(
    image_path: str,
    lang: str,
    psm: int = 3,
    oem: int = 3,
    tessdata_dir: str | None = None,
    apply_deskew: bool = True,
    apply_clahe: bool = True,
    # apply_denoise: bool = True, # Added - REMOVED
    # denoise_strength: int = DEFAULT_DENOISE_STRENGTH, # Added - REMOVED
    # apply_morph_open: bool = True, # Added - REMOVED
    blur_type: str = "Gaussian",
    apply_spellcheck: bool = True
) -> Tuple[OcrResult, Optional[np.ndarray]]: # Return type still includes processed_img_np for potential preview
    """Performs OCR, returning structured data and the final processed image array."""
    print(f"Performing OCR on: {image_path} with lang='{lang}', psm={psm}, oem={oem}, blur='{blur_type}'")
    if tessdata_dir:
        print(f"Using tessdata directory: {tessdata_dir}")

    # Update config to use the provided PSM and OEM
    config = f'--oem {oem} --psm {psm} -l {lang}'
    if tessdata_dir and os.path.isdir(tessdata_dir):
        safe_tessdata_dir = tessdata_dir.replace("\\", "/")
        # Pass the path without explicit quotes; pytesseract should handle it
        config += f' --tessdata-dir {safe_tessdata_dir}'
        print(f"Tesseract config updated with tessdata_dir: {config}")

    processed_img_np: Optional[np.ndarray] = None # Initialize
    try:
        # 1. Conditionally preprocess the image using OpenCV
        processed_img_np = preprocess_image_for_ocr(
            image_path,
            apply_deskew=apply_deskew,
            apply_clahe=apply_clahe,
            # apply_denoise=apply_denoise, # REMOVED
            # denoise_strength=denoise_strength, # REMOVED
            # apply_morph_open=apply_morph_open, # REMOVED
            blur_type=blur_type
        )
        # Get dimensions AFTER preprocessing
        processed_height, processed_width = processed_img_np.shape[:2]

        # 2. Call pytesseract.image_to_data
        print(f"Running pytesseract.image_to_data with config: {config}")
        ocr_data_dict = pytesseract.image_to_data(
            processed_img_np,
            config=config,
            output_type=pytesseract.Output.DICT
        )
        # print("Tesseract Raw Output Keys:", ocr_data_dict.keys())
        # print("Sample Raw Data (conf):", ocr_data_dict.get('conf', [])[:10])

        # 3. Process the dictionary output
        full_text_list = []
        num_boxes = len(ocr_data_dict['text'])

        if num_boxes == 0:
            print("Tesseract returned no text boxes.")

        for i in range(num_boxes):
            try:
                # Filter based on confidence from Tesseract and non-empty text
                confidence_val = float(ocr_data_dict['conf'][i])
                text = str(ocr_data_dict['text'][i]).strip()

                # Filter based on confidence and non-empty text
                if confidence_val >= MIN_OCR_CONFIDENCE and text:
                    # No longer creating WordData instances here for the words list
                    full_text_list.append(text)
            except (ValueError, TypeError, KeyError, IndexError) as e:
                # Log if a specific box fails processing, but continue
                print(f"Warning: Skipping box index {i} due to data error: {e} - Data: {{key: ocr_data_dict.get(key, [None]*num_boxes)[i] for key in ocr_data_dict}}")
                continue

        print(f"Processed {len(full_text_list)} words with confidence >= {MIN_OCR_CONFIDENCE}%")
        raw_extracted_text = " ".join(full_text_list).strip()

        # 4. Conditionally apply post-processing
        if apply_spellcheck:
            final_text = postprocess_text(raw_extracted_text, lang)
        else:
            print("Skipping spell check.")
            final_text = raw_extracted_text

        # 5. Create the result object
        ocr_result = OcrResult(
            # words=[], # words attribute removed from OcrResult
            full_text=final_text,
            processed_image_width=processed_width, # Width of image passed to Tesseract
            processed_image_height=processed_height # Height of image passed to Tesseract
        )
        # Return both the result and the image array used for OCR
        return ocr_result, processed_img_np

    except pytesseract.TesseractNotFoundError:
        print("TesseractNotFoundError encountered in perform_ocr")
        raise # Re-raise the specific error

    except ValueError as ve:
        print(f"Error during preprocessing step: {ve}")
        raise

    except Exception as e:
        print(f"Error during OCR processing: {e}")
        import traceback
        traceback.print_exc()
        raise RuntimeError(f"An unexpected error occurred during OCR: {type(e).__name__}") 