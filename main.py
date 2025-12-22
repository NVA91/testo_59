#!/usr/bin/env python3
"""
Home Automation Starter Project
"""

import sys
from pathlib import Path

# Venv check
venv_path = Path(__file__).parent / "venv"
if not venv_path.exists():
    print("❌ ERROR: venv nicht gefunden!")
    sys.exit(1)

print("✅ Home Automation Project gestartet!")
print(f"📁 Project Path: {Path(__file__).parent}")
print(f"🐍 Python: {sys.version}")
print("\n🎯 Bereit für Home Automation!")
