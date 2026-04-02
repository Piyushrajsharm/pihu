import psutil
import subprocess
import os
import json

def get_gpu_info():
    """Get GPU info using wmic on Windows."""
    try:
        cmd = 'wmic path win32_VideoController get name,AdapterRAM /format:list'
        output = subprocess.check_output(cmd, shell=True).decode('utf-8')
        gpus = []
        current_gpu = {}
        for line in output.split('\n'):
            line = line.strip()
            if not line: continue
            if '=' in line:
                key, val = line.split('=', 1)
                current_gpu[key.strip()] = val.strip()
                if len(current_gpu) == 2:
                    gpus.append(current_gpu)
                    current_gpu = {}
        return gpus
    except Exception as e:
        return [{"Name": "Unknown", "AdapterRAM": "0"}]

def benchmark():
    # 1. System RAM
    ram_gb = round(psutil.virtual_memory().total / (1024**3), 2)
    
    # 2. GPU VRAM
    gpu_info = get_gpu_info()
    vram_mb = 0
    gpu_name = "Unknown"
    for gpu in gpu_info:
        name = gpu.get('Name', '')
        ram = int(gpu.get('AdapterRAM', '0')) / (1024**2)
        if ram > vram_mb:
            vram_mb = ram
            gpu_name = name
            
    vram_gb = round(vram_mb / 1024, 2)
    
    # 3. Recommendation Logic
    recommendation = {
        "hardware": {
            "ram_gb": ram_gb,
            "gpu_name": gpu_name,
            "vram_gb": vram_gb
        }
    }
    
    if ram_gb >= 16 and vram_gb >= 4:
        recommendation["primary_model"] = "llama3.1:8b"
        recommendation["quantization"] = "Q4_K_M"
        recommendation["turboquant_kv"] = "q4_0"
        recommendation["explanation"] = "Your 16GB RAM and 4GB+ VRAM can comfortably handle Llama 3.1 8B with 4-bit KV cache compression (TurboQuant)."
    elif ram_gb >= 8:
        recommendation["primary_model"] = "phi3.5:mini"
        recommendation["quantization"] = "Q4_K_M"
        recommendation["turboquant_kv"] = "q4_0"
        recommendation["explanation"] = "Phi-3.5-mini is ideal for fast, high-quality chat on 8GB-12GB setups."
    else:
        recommendation["primary_model"] = "qwen2.5:0.5b"
        recommendation["quantization"] = "Q8_0"
        recommendation["turboquant_kv"] = "none"
        recommendation["explanation"] = "Low RAM detected. Using ultra-lightweight Qwen 0.5B."

    return recommendation

if __name__ == "__main__":
    results = benchmark()
    print(json.dumps(results, indent=4))
