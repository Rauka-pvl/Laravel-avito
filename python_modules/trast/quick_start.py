#!/usr/bin/env python3
"""
Quick start script for Trast parser on server.

This script handles installation and first run.
"""

import subprocess
import sys
import os

def main():
    """Quick start for server deployment."""
    print("🚀 Trast Parser - Quick Start")
    print("=" * 40)
    
    # Check if we're in the right directory
    if not os.path.exists('requirements.txt'):
        print("❌ requirements.txt not found. Run this script from the parser directory.")
        return 1
    
    # Install dependencies
    print("📦 Installing dependencies...")
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
        ])
        print("✅ Dependencies installed")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        return 1
    
    # Test components
    print("\n🧪 Testing components...")
    try:
        subprocess.check_call([sys.executable, "test_parser.py"])
        print("✅ Components test passed")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Components test failed: {e}")
        print("   Continuing anyway...")
    
    # Run parser
    print("\n🎯 Running parser...")
    try:
        subprocess.check_call([sys.executable, "main.py"])
        print("✅ Parser completed successfully")
    except subprocess.CalledProcessError as e:
        print(f"❌ Parser failed: {e}")
        return 1
    
    print("\n🎉 All done!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
