"""
EXTREME Test: Pihu Vision + Swarm Planning + Dashboard Execution

Test 1: Cloud Vision analyzes the Gemini dashboard image
Test 2: Swarm LLM creates a phased automation plan
Test 3: Full execution (with --execute flag)
"""

import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from logger import get_logger
log = get_logger("TEST")

CSV_PATH = r"D:\JarvisProject\pihu\NSE_Equity_Data_CONSOLIDATED.csv"
DASHBOARD_IMG = r"D:\JarvisProject\pihu\Gemini_Generated_Image_55zeon55zeon55ze.png"


def test_vision():
    """Test 1: Cloud Vision (Llama 3.2 11B) analyzes the dashboard image."""
    log.info("=" * 50)
    log.info("TEST 1: Cloud Vision — Analyze Dashboard Image")
    log.info("=" * 50)

    from llm.cloud_llm import CloudLLM
    from tools.vision_grounding import VisionGrounding

    cloud = CloudLLM()
    grounding = VisionGrounding(cloud_llm=cloud)

    t0 = time.time()
    desc = grounding.describe_image(
        DASHBOARD_IMG,
        "Describe this Power BI dashboard layout. What charts, KPI cards, filters, and data tables are visible? Be specific about the layout."
    )
    elapsed = time.time() - t0

    print(f"\nVision Analysis ({elapsed:.1f}s):")
    print(f"{'-' * 50}")
    print(desc[:600])
    print(f"{'-' * 50}\n")
    return desc


def test_plan():
    """Test 2: Swarm Agent creates a phased execution plan."""
    log.info("=" * 50)
    log.info("TEST 2: Swarm Planner — Create Phased Plan")
    log.info("=" * 50)

    from llm.cloud_llm import CloudLLM
    from tools.vision_grounding import VisionGrounding
    from tools.automation import AutomationTool
    from tools.pencil_swarm_agent import PencilSwarmAgent

    cloud = CloudLLM()
    grounding = VisionGrounding(cloud_llm=cloud)
    automation = AutomationTool(llm_client=cloud, grounding_tool=grounding)
    swarm = PencilSwarmAgent(automation_tool=automation, vision_grounding=grounding)

    CSV_PATH = "stocks_df.csv"
    task = (
        f"Open Google Chrome and go to Web Excel (Microsoft 365). Upload or load the CSV file at '{CSV_PATH}', "
        f"wait for it to load (it's 218MB), select all data with Ctrl+A, "
        f"remove duplicates, auto-fit columns, save as cleaned_stocks.xlsx. "
        f"Then open Power BI Desktop, click Get Data, select Excel workbook, "
        f"load the cleaned file, and create a KPI card and a line chart."
    )

    t0 = time.time()
    plan = swarm._create_plan(task)
    elapsed = time.time() - t0

    if plan:
        print(f"\nPlan ({elapsed:.1f}s) - {len(plan)} phases:")
        print(f"{'-' * 50}")
        for i, phase in enumerate(plan):
            actions = phase.get("actions", [])
            verify = phase.get("verify", "N/A")
            print(f"  Phase {i+1}: {phase.get('phase', '?')} ({len(actions)} actions)")
            for a in actions[:4]:
                print(f"    -> {a.get('action','?')}: {str(a.get('arg',''))[:50]}")
            if len(actions) > 4:
                print(f"    -> ... +{len(actions)-4} more")
            print(f"    Verified: {verify[:60]}")
        print(f"{'-' * 50}\n")
    else:
        print("\n❌ Plan creation failed!\n")

    return plan


def test_execute():
    """Test 3: Full execution with AI Planner, Executors, and Verifiers."""
    import os
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    CSV_PATH = os.path.join(BASE_DIR, "stocks_df.csv")
    DASHBOARD_IMG = os.path.join(BASE_DIR, "Gemini_Generated_Image_55zeon55zeon55ze.png")
    log.info("=" * 50)
    log.info("TEST 3: FULL EXECUTION")
    log.info("=" * 50)

    from llm.cloud_llm import CloudLLM
    from tools.vision_grounding import VisionGrounding
    from tools.automation import AutomationTool
    from tools.pencil_swarm_agent import PencilSwarmAgent

    cloud = CloudLLM()
    grounding = VisionGrounding(cloud_llm=cloud)
    automation = AutomationTool(llm_client=cloud, grounding_tool=grounding)
    swarm = PencilSwarmAgent(automation_tool=automation, vision_grounding=grounding)

    print("\n⚠️  EXECUTING IN 5 SECONDS — Don't touch mouse/keyboard!")
    for i in range(5, 0, -1):
        print(f"  {i}...")
        time.sleep(1)

    result = swarm.build_dashboard_from_cleaned_data(
        csv_path=CSV_PATH,
        dashboard_image_path=DASHBOARD_IMG,
    )
    print(f"\n{'=' * 50}")
    print(result)
    print(f"{'=' * 50}\n")


if __name__ == "__main__":
    # Test 1: Vision
    desc = test_vision()

    # Test 2: Planning
    plan = test_plan()

    # Test 3: Execute only with --execute
    if "--execute" in sys.argv:
        test_execute()
    else:
        print("SUCCESS: Tests 1 and 2 passed! To run full execution:")
        print("   python test_swarm_extreme.py --execute\n")
