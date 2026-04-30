"""
Pihu Test Suite — Shared Fixtures
"""
import sys
import os
from pathlib import Path

# Ensure pihu root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ["PIHU_ENV"] = "testing"
