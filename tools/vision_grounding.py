"""
Pihu — Vision Grounding (Hybrid: Cloud Vision + Local Fallback)
Uses NVIDIA NIM Cloud Vision (Llama 3.2 11B) for spatial reasoning.
Falls back to local Ollama for text-only queries.
"""

import base64
import io
import re
import time
from PIL import Image, ImageGrab, ImageDraw, ImageFont
from logger import get_logger

log = get_logger("GROUNDING")


class VisionGrounding:
    """Spatial grounding — locating UI elements on screen via Cloud Vision."""

    def __init__(self, cloud_llm=None):
        self.cloud_llm = cloud_llm
        log.info("VisionGrounding initialized | using Cloud Vision (Llama 3.2 11B)")

    def _screenshot_to_b64(self, max_width=1024) -> tuple[str, int, int]:
        """Capture screen and return (base64_jpg, width, height)."""
        screenshot = ImageGrab.grab()
        width, height = screenshot.size
        
        # Resize for efficiency
        if width > max_width:
            ratio = max_width / width
            new_h = int(height * ratio)
            screenshot = screenshot.resize((max_width, new_h))
            width, height = max_width, new_h
        
        # Convert to JPEG base64
        screenshot = screenshot.convert("RGB")
        buf = io.BytesIO()
        screenshot.save(buf, format="JPEG", quality=75)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return b64, width, height

    def _image_file_to_b64(self, path: str, max_width=1024) -> tuple[str, int, int]:
        """Load image file and return (base64_jpg, width, height)."""
        img = Image.open(path).convert("RGB")
        width, height = img.size
        
        if width > max_width:
            ratio = max_width / width
            new_h = int(height * ratio)
            img = img.resize((max_width, new_h))
            width, height = max_width, new_h
        
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return b64, width, height

    def _draw_grid_and_get_b64(self, max_width=1280) -> tuple[str, dict]:
        """Capture screen, overlay 20x15 grid, and return (base64_jpg, cell_map)."""
        screenshot = ImageGrab.grab()
        orig_w, orig_h = screenshot.size
        width, height = orig_w, orig_h
        
        # Resize for efficiency and VLM token limits
        if width > max_width:
            ratio = max_width / width
            new_h = int(height * ratio)
            screenshot = screenshot.resize((max_width, new_h))
            width, height = max_width, new_h
        
        screenshot = screenshot.convert("RGB")
        draw = ImageDraw.Draw(screenshot)
        
        # 20 columns, 15 rows (A-O)
        cols, rows = 20, 15
        cell_w = width / cols
        cell_h = height / rows
        
        try:
            font = ImageFont.truetype("arialbd.ttf", size=int(min(cell_w, cell_h) * 0.4))
        except:
            font = ImageFont.load_default()
            
        cell_map = {}
        
        # Draw grid lines
        for r in range(rows + 1):
            y = r * cell_h
            draw.line([(0, y), (width, y)], fill=(255, 0, 0), width=1)
        for c in range(cols + 1):
            x = c * cell_w
            draw.line([(x, 0), (x, height)], fill=(255, 0, 0), width=1)
            
        # Draw labels
        for r in range(rows):
            for c in range(cols):
                # Excel style: Column Letter (A-T), Row Number (0-14)
                label = f"{chr(65 + c)}{r}" 
                
                # Center of cell
                cx = (c + 0.5) * cell_w
                cy = (r + 0.5) * cell_h
                
                # Map back to original screen coordinates for clicking
                orig_cx = int(cx / (width / orig_w))
                orig_cy = int(cy / (height / orig_h))
                cell_map[label] = (orig_cx, orig_cy)
                
                # Draw text background
                try:
                    bbox = draw.textbbox((0, 0), label, font=font)
                    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                except:
                    tw, th = draw.textsize(label, font=font)
                
                tx, ty = cx - tw/2, cy - th/2
                draw.rectangle([tx-2, ty-2, tx+tw+2, ty+th+2], fill=(0,0,0,180))
                draw.text((tx, ty), label, fill=(255, 255, 0), font=font)
                
        buf = io.BytesIO()
        screenshot.save(buf, format="JPEG", quality=85)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return b64, cell_map

    def find_element(self, description: str) -> tuple[int, int] | None:
        """Find a UI element on screen using Grid Overlay and return its (X, Y) center."""
        log.info("🎯 Finding element: %s", description)
        
        try:
            b64, cell_map = self._draw_grid_and_get_b64()
            
            prompt = (
                f"You are a UI agent. I have drawn a red grid over the screen. "
                f"Each grid cell has a yellow label (e.g., A5, B12) at its center. "
                f"Find the exact grid cell that contains the element: '{description}'. "
                f"Return ONLY the grid label containing the center of this element. "
                f"Do not write any other text. If not found, return ONLY 'NONE'."
            )
            
            t0 = time.time()
            response = self.cloud_llm.generate_vision(prompt, b64)
            elapsed = (time.time() - t0) * 1000
            
            if not response or "NONE" in response.upper():
                log.warning("Cloud Vision returned NONE")
                return None
                
            # Parse the grid label (e.g. A0..T14)
            match = re.search(r"([A-Ta-t]\d{1,2})", response)
            if match:
                label = match.group(1).upper()
                if label in cell_map:
                    x, y = cell_map[label]
                    log.info("🎯 Found '%s' in cell %s -> (%d, %d)", description, label, x, y)
                    return (x, y)
                else:
                    log.warning("❌ Invalid grid label returned: %s", label)
                    return None
            
            log.warning("⚠️ Could not parse cell from response: %s", response[:80])
            return None

        except Exception as e:
            log.error("Vision grounding failed: %s", e)
            return None

    def describe_screen(self, question: str = "Describe what is on the screen.") -> str:
        """Capture and describe the current screen."""
        try:
            b64, w, h = self._screenshot_to_b64()
            t0 = time.time()
            result = self.cloud_llm.generate_vision(question, b64)
            elapsed = (time.time() - t0) * 1000
            log.info("👁️ Screen description in %.0fms (%d chars)", elapsed, len(result or ""))
            return result or "Could not describe screen."
        except Exception as e:
            log.error("Screen description failed: %s", e)
            return f"Vision failed: {e}"

    def describe_image(self, image_path: str, question: str = "Describe this image in detail.") -> str:
        """Analyze an image file using Cloud Vision."""
        try:
            b64, w, h = self._image_file_to_b64(image_path)
            t0 = time.time()
            result = self.cloud_llm.generate_vision(question, b64)
            elapsed = (time.time() - t0) * 1000
            log.info("👁️ Image analysis in %.0fms (%d chars)", elapsed, len(result or ""))
            return result or "Could not analyze image."
        except Exception as e:
            log.error("Image analysis failed: %s", e)
            return f"Vision failed: {e}"

    def verify_state(self, expected: str) -> bool:
        """Verify whether the screen currently shows the expected state."""
        desc = self.describe_screen(
            f'Does the screen currently show: "{expected}"? Answer ONLY "yes" or "no".'
        )
        return "yes" in desc.lower()
