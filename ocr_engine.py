"""
Pihu V2 — OCR Vision Engine (The Eyes)
Replaces manual clipboard hooks with instantaneous PyTorch-backed screen ripping using python-docTR.
"""
from logger import get_logger
import os
import tempfile

log = get_logger("OCR")

class OCREngine:
    def __init__(self):
        self.is_available = True
        self.model = None
        self._check_dependencies()

    def _check_dependencies(self):
        try:
            import doctr
            import pyautogui
            import PIL
        except ImportError:
            log.warning("docTR or PyAutoGUI missing. Run `pip install \"python-doctr[torch]\" pyautogui`")
            self.is_available = False

    def _lazy_load_model(self):
        """Pretrained PyTorch model is extremely heavy. Loaded exactly once during first vision intent."""
        if not self.model and self.is_available:
            try:
                log.info("👁️ Booting docTR PyTorch Vision Framework... (This takes 5s on first boot)")
                from doctr.models import ocr_predictor
                # ResNet50 + CRNN architecture for dense VSCode/Terminal text extraction
                self.model = ocr_predictor(det_arch='db_resnet50', reco_arch='crnn_vgg16_bn', pretrained=True)
                log.info("👁️ Vision Framework Active.")
            except Exception as e:
                log.error("docTR Model failed to load into memory: %s", e)
                self.is_available = False

    def get_screen_text(self, max_length: int = 4000) -> str:
        """
        Takes an instant snapshot of the active screen and rips all visible text.
        Truncates explicitly so context windows don't explode on wide-monitor setups.
        """
        if not self.is_available:
            return ""
            
        try:
            self._lazy_load_model()
            if not self.model:
                return ""

            import pyautogui
            from doctr.io import DocumentFile
            
            # Snap active environment using proper temp file
            tmp_fd, screenshot_path = tempfile.mkstemp(suffix=".png", prefix="pihu_ocr_")
            os.close(tmp_fd)
            try:
                pyautogui.screenshot(screenshot_path)
                
                # Extract
                doc = DocumentFile.from_images(screenshot_path)
                result = self.model(doc)
                
                extracted_text = ""
                json_output = result.export()
                
                for page in json_output.get('pages', []):
                    for block in page.get('blocks', []):
                        for line in block.get('lines', []):
                            for word in line.get('words', []):
                                extracted_text += word.get('value', '') + " "
                            extracted_text += "\n"
            finally:
                # Always clean up temp file
                if os.path.exists(screenshot_path):
                    os.remove(screenshot_path)
                    
            stripped = extracted_text.strip()
            log.info("👁️ docTR successfully ripped %d characters from active screen.", len(stripped))
            
            # Extreme Context Protection
            return stripped[-max_length:] if len(stripped) > max_length else stripped
            
        except Exception as e:
            log.error(f"docTR Screen Rip Failed: {e}")
            return ""
