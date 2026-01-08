#!/usr/bin/env python3
"""
NAYAN-AI System Verification & Quick Test
Run this to verify your system is ready to launch
"""

import sys
import os
from pathlib import Path

def check_file_exists(path, description):
    """Check if a file exists"""
    if Path(path).exists():
        print(f"✓ {description}: {path}")
        return True
    else:
        print(f"✗ MISSING {description}: {path}")
        return False

def main():
    print("=" * 60)
    print("NAYAN-AI SYSTEM VERIFICATION")
    print("=" * 60)
    print()
    
    project_root = Path(__file__).parent
    checks_passed = 0
    total_checks = 0
    
    # Frontend files
    print("🌐 Frontend Files:")
    frontend_files = [
        ("frontend/login.html", "Login Page"),
        ("frontend/signin.html", "Registration Page"),
        ("frontend/index.html", "Dashboard"),
        ("frontend/cataract.html", "Cataract Page"),
        ("frontend/dryeye.html", "Dry Eye Page"),
        ("frontend/history.html", "History Page"),
        ("frontend/report.html", "Comprehensive Report"),
        ("frontend/assets/js/app.js", "App Logic"),
        ("frontend/assets/js/cataract.js", "Cataract Logic"),
        ("frontend/assets/js/dryeye.js", "Dry Eye Logic"),
        ("frontend/assets/js/history.js", "History Logic"),
        ("frontend/assets/js/report.js", "Report Logic"),
    ]
    
    for file_path, desc in frontend_files:
        total_checks += 1
        if check_file_exists(project_root / file_path, desc):
            checks_passed += 1
    
    print()
    
    # Backend files
    print("🔧 Backend Files:")
    backend_files = [
        ("backend/app.py", "Main Server"),
        ("backend/requirements.txt", "Dependencies"),
        ("backend/catract/artifacts/cataract_mobilenetv2.keras", "DL Model"),
        ("backend/catract/artifacts/labels.json", "Model Labels"),
    ]
    
    for file_path, desc in backend_files:
        total_checks += 1
        if check_file_exists(project_root / file_path, desc):
            checks_passed += 1
    
    print()
    
    # Configuration files
    print("⚙️ Configuration:")
    config_files = [
        ("START_BACKEND.bat", "Startup Script"),
        (".vscode/settings.json", "VS Code Settings"),
    ]
    
    for file_path, desc in config_files:
        total_checks += 1
        if check_file_exists(project_root / file_path, desc):
            checks_passed += 1
    
    print()
    print("=" * 60)
    print(f"VERIFICATION RESULT: {checks_passed}/{total_checks} checks passed")
    print("=" * 60)
    print()
    
    if checks_passed == total_checks:
        print("✅ ALL CHECKS PASSED! System is ready to launch.")
        print()
        print("🚀 Next Steps:")
        print("1. Install dependencies:")
        print("   D:\\python\\intepretor\\Scripts\\python.exe -m pip install -r backend\\requirements.txt")
        print()
        print("2. Start the backend:")
        print("   START_BACKEND.bat")
        print()
        print("3. Open browser:")
        print("   http://127.0.0.1:5000")
        print()
        print("4. Test the system:")
        print("   - Register a new account or use Demo Login")
        print("   - Fill patient information")
        print("   - Run screenings (Cataract/Dry Eye)")
        print("   - View comprehensive report")
        return 0
    else:
        print("⚠️ SOME FILES ARE MISSING!")
        print("Please ensure all files are present before starting.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
