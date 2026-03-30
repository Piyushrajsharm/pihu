from llm.cloud_llm import CloudLLM
from tools.automation import AutomationTool
import time

def run_extreme_test():
    print("Initializing Cloud LLM and Automation Agent...")
    llm = CloudLLM()
    auto = AutomationTool(llm_client=llm)
    
    print("\n⚠️ Starting extreme OS test in 3 seconds. Please do not touch your mouse or keyboard...")
    time.sleep(1)
    print("2...")
    time.sleep(1)
    print("1...")
    time.sleep(1)
    
    command = "pehle notepad kholo aur usme likho Hello Piyush! Pihu reporting for duty., uske baad enter dabao, aur type karo This is the extreme OS automation test!, phir calculator kholo, usme type karo 888*888, aur enter press karo, then volume up karo"
    
    print(f"\n🗣️ Natural Command: '{command}'")
    print("-" * 50)
    
    result = auto.execute_natural(command)
    print("\n✅ Final Result:")
    print(result)

if __name__ == "__main__":
    run_extreme_test()
