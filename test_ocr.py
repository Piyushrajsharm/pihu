"""
Pihu V2 — docTR PyTorch Vision Sandbox
Validates that the lazy-loaded docTR OCR module installs properly, instantiates
the ResNet50 framework, and rips string payloads successfully from the active screen.
"""
from ocr_engine import OCREngine
import time

def run_vision_test():
    print("========== V2 EYES BOOT SEQUENCE ==========")
    ocr = OCREngine()
    
    if not ocr.is_available:
        print("[CRITICAL ERROR] docTR failed to initialize. Ensure pip install \"python-doctr[torch]\" was executed.")
        return
        
    print("\n>>> Phase 1: Triggering Lazy-Load Model Weights (Expect ~5-10s)")
    
    # We create a dummy test string on screen by printing it, so the screenshot sees it
    print("\n[TARGET VISUAL STRING]: <<PIHU_VISION_V2_TEST_SUCCESS>>\n")
    
    start_time = time.time()
    extracted = ocr.get_screen_text(max_length=5000)
    end_time = time.time()
    
    # Check if the target string was ripped from the terminal screen
    success = "PIHU_VISION_V2_TEST" in extracted
    
    print(f"\nExtraction Latency (Including Boot): {(end_time - start_time):.2f} seconds")
    print(f"Target String Found in OCR: {'✅ YES' if success else '❌ NO'}")
    
    print(f"\n[RAW OCR DUMP (Sample)]:\n{extracted[-500:]}")
    print("\n========== V2 EYES TEST COMPLETE ==========")

if __name__ == "__main__":
    run_vision_test()
