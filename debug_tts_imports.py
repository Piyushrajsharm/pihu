import traceback
import sys
import os

# Add third_party to path if needed (though it should be there if installed in -e)
try:
    print("Attempting to import TTS.tts.configs.fast_pitch_config...")
    import TTS.tts.configs.fast_pitch_config
    print("Successfully imported fast_pitch_config!")
except Exception as e:
    print("\n--- IMPORT ERROR TRACEBACK ---")
    traceback.print_exc()
    print("------------------------------")

try:
    print("\nAttempting to import TTS.tts.models.forward_tts...")
    import TTS.tts.models.forward_tts
    print("Successfully imported forward_tts model!")
except Exception as e:
    print("\n--- MODEL IMPORT ERROR TRACEBACK ---")
    traceback.print_exc()
    print("------------------------------")
