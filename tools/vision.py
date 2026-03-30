"""
Pihu — Vision Tool
Screen capture and image analysis using gemma3:4b via Ollama.
"""

import io
import base64
import time

from logger import get_logger

log = get_logger("VISION")


class VisionTool:
    """Vision analysis tool.
    
    - analyze_screen(): Captures screen, sends to vision model
    - analyze_image(path): Analyzes a specific image file
    - Prefers GPU execution, falls back to CPU via scheduler
    """

    def __init__(self, scheduler=None):
        from config import VISION_MODEL, OLLAMA_BASE_URL
        import ollama

        self.model = VISION_MODEL
        self.client = ollama.Client(host=OLLAMA_BASE_URL)
        self.scheduler = scheduler

        log.info("VisionTool initialized | model=%s", self.model)

    def analyze_screen(self, question: str = "What is on the screen?") -> str:
        """Capture screen and analyze with vision model.
        
        Args:
            question: What to look for / analyze

        Returns:
            Description string from vision model
        """
        log.info("👁️ Capturing screen...")

        try:
            from PIL import ImageGrab

            # Capture screen
            screenshot = ImageGrab.grab()

            # Resize for efficiency (max 1024px wide)
            max_w = 1024
            if screenshot.width > max_w:
                ratio = max_w / screenshot.width
                new_size = (max_w, int(screenshot.height * ratio))
                screenshot = screenshot.resize(new_size)

            # Convert to bytes
            img_buffer = io.BytesIO()
            screenshot.save(img_buffer, format="PNG")
            img_bytes = img_buffer.getvalue()

            log.info(
                "📸 Screenshot captured: %dx%d (%.1f KB)",
                screenshot.width, screenshot.height, len(img_bytes) / 1024,
            )

            # Send to vision model
            return self._analyze_bytes(img_bytes, question)

        except Exception as e:
            log.error("Screen capture failed: %s", e)
            return f"Screen capture failed: {str(e)}"

    def analyze_image(self, image_path: str, question: str = "Describe this image.") -> str:
        """Analyze an image file.
        
        Args:
            image_path: Path to image file
            question: What to analyze

        Returns:
            Description string
        """
        log.info("👁️ Analyzing image: %s", image_path)

        try:
            with open(image_path, "rb") as f:
                img_bytes = f.read()

            return self._analyze_bytes(img_bytes, question)

        except FileNotFoundError:
            return f"Image not found: {image_path}"
        except Exception as e:
            log.error("Image analysis failed: %s", e)
            return f"Image analysis failed: {str(e)}"

    def _analyze_bytes(self, img_bytes: bytes, question: str) -> str:
        """Send image bytes to vision model for analysis."""
        t0 = time.time()

        try:
            response = self.client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": question,
                        "images": [img_bytes],
                    }
                ],
            )

            result = response.get("message", {}).get("content", "")
            elapsed_ms = (time.time() - t0) * 1000

            log.info(
                "👁️ Vision analysis complete in %.0fms | %d chars",
                elapsed_ms, len(result),
            )

            return result

        except Exception as e:
            log.error("Vision model inference failed: %s", e)
            if self.scheduler:
                self.scheduler.on_gpu_crash()
            return f"Vision analysis failed: {str(e)}"
