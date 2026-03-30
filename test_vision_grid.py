import sys
from pathlib import Path

# Add root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from llm.cloud_llm import CloudLLM
from tools.vision_grounding import VisionGrounding

def main():
    print("====================================")
    print("Testing Vision Grid Grounding")
    print("====================================")
    
    cloud = CloudLLM()
    grounding = VisionGrounding(cloud_llm=cloud)
    
    # Try to find a very common UI element that should be on screen
    # e.g., the Windows Start button, or VS Code icon
    element = "Windows Start button or search bar"
    print(f"👁️ Asking Cloud Vision to find: '{element}'...")
    
    coords = grounding.find_element(element)
    
    if coords:
        print(f"✅ Success! Element found at absolute screen coordinates: {coords}")
        
        # Test drawing the image locally so we can see the grid
        print("📸 Saving grid preview to 'grid_preview.jpg'...")
        b64, cm = grounding._draw_grid_and_get_b64()
        import base64
        with open("grid_preview.jpg", "wb") as f:
            f.write(base64.b64decode(b64))
        print("✅ Saved grid_preview.jpg")
    else:
        print("❌ Failed. Element not found or grid parsing failed.")

if __name__ == "__main__":
    main()
