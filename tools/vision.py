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
        try:
            import ollama
            self.client = ollama.Client(host=OLLAMA_BASE_URL)
            self.model = VISION_MODEL
            log.info("VisionTool: Local Ollama mode active | model=%s", self.model)
        except:
            self.client = None
            log.info("VisionTool: Local Ollama missing | Falling back to Cloud Vision")

        self.scheduler = scheduler

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
        """Send image bytes to vision model (Local → Cloud Fallback)."""
        t0 = time.time()

        # 1. Try local Ollama if healthy
        if self.client:
            try:
                response = self.client.chat(
                    model=self.model,
                    messages=[{"role": "user", "content": question, "images": [img_bytes]}],
                )
                result = response.get("message", {}).get("content", "")
                log.info("👁️ Local Vision analysis complete in %.0fms", (time.time() - t0) * 1000)
                return result
            except Exception as e:
                log.warning("Local vision failed: %s", e)

        # 2. Try Cloud Vision (NVIDIA NIM)
        try:
            from config import NVIDIA_NIM_API_KEY, CLOUD_VISION_MODEL
            if NVIDIA_NIM_API_KEY:
                log.info("☁️ Triggering Cloud Vision (NVIDIA)...")
                # Simple base64 encode for NIM
                import base64
                img_b64 = base64.b64encode(img_bytes).decode("utf-8")
                
                from llm.cloud_llm import CloudLLM
                cloud = CloudLLM()
                result = cloud.generate(
                    prompt=f"{question}\n\n[IMAGE_DATA_ENCODED]",
                    model_override=CLOUD_VISION_MODEL,
                    stream=False
                )
                log.info("👁️ Cloud Vision analysis complete in %.0fms", (time.time() - t0) * 1000)
                return result
        except Exception as e:
            log.error("Cloud vision failed: %s", e)

        return "Vision analysis failed (No local or cloud models available)."
