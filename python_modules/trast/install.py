#!/usr/bin/env python3
"""
Installation script for Trast parser.

Installs dependencies and sets up the environment.
"""

import subprocess
import sys
import os

def install_requirements():
    """Install required packages."""
    print("📦 Installing dependencies...")
    
    try:
        # Try to install with --upgrade to handle version conflicts
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "--upgrade"
        ])
        print("✅ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        print("💡 Trying to install without --upgrade...")
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
            ])
            print("✅ Dependencies installed successfully (without upgrade)")
            return True
        except subprocess.CalledProcessError as e2:
            print(f"❌ Failed to install dependencies: {e2}")
            return False

def check_browser():
    """Check if Chrome/Firefox is available."""
    print("🔍 Checking browser availability...")
    
    browsers = {
        'chrome': ['google-chrome', 'chrome', 'chromium-browser', 'chromium', 'google-chrome-stable'],
        'firefox': ['firefox', 'firefox-esr']
    }
    
    available = []
    
    for browser_type, commands in browsers.items():
        for cmd in commands:
            try:
                result = subprocess.run([cmd, '--version'], 
                                      capture_output=True, 
                                      text=True, 
                                      timeout=5)
                if result.returncode == 0:
                    available.append(browser_type)
                    print(f"✅ {browser_type.title()} found")
                    break
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
    
    # Additional check for Chrome in common Linux locations
    if 'chrome' not in available:
        chrome_paths = [
            '/usr/bin/google-chrome',
            '/usr/bin/chromium-browser',
            '/usr/bin/chromium',
            '/opt/google/chrome/chrome'
        ]
        for path in chrome_paths:
            if os.path.exists(path):
                available.append('chrome')
                print(f"✅ Chrome found at {path}")
                break
    
    if not available:
        print("⚠️ No browsers found. Selenium fallback may not work.")
        print("   Install Chrome or Firefox for Cloudflare bypass:")
        print("   - Ubuntu/Debian: sudo apt install google-chrome-stable")
        print("   - CentOS/RHEL: sudo yum install google-chrome-stable")
    else:
        print(f"✅ Available browsers: {', '.join(available)}")
    
    return len(available) > 0

def check_tor():
    """Check if TOR is available."""
    print("🔍 Checking TOR availability...")
    
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', 9050))
        sock.close()
        
        if result == 0:
            print("✅ TOR is running on port 9050")
            return True
        else:
            print("⚠️ TOR not running on port 9050")
            print("   Install and start TOR for anonymity:")
            print("   - Linux: sudo apt install tor && sudo systemctl start tor")
            print("   - Windows: Download Tor Browser")
            return False
    except Exception as e:
        print(f"⚠️ Error checking TOR: {e}")
        return False

def check_warp():
    """Check if WARP is available."""
    print("🔍 Checking WARP availability...")
    
    try:
        result = subprocess.run(['warp-cli', 'status'], 
                              capture_output=True, 
                              text=True, 
                              timeout=5)
        if result.returncode == 0:
            if 'Connected' in result.stdout:
                print("✅ WARP is connected")
                return True
            else:
                print("⚠️ WARP installed but not connected")
                print("   Run: warp-cli connect")
                return False
        else:
            print("⚠️ WARP not installed")
            print("   Install Cloudflare WARP for better performance")
            return False
    except FileNotFoundError:
        print("⚠️ WARP not installed")
        print("   Install Cloudflare WARP for better performance")
        return False
    except Exception as e:
        print(f"⚠️ Error checking WARP: {e}")
        return False

def main():
    """Main installation process."""
    print("🚀 Trast Parser Installation")
    print("=" * 40)
    
    # Check if we're in the right directory
    if not os.path.exists('requirements.txt'):
        print("❌ requirements.txt not found. Run this script from the parser directory.")
        return 1
    
    # Install dependencies
    if not install_requirements():
        return 1
    
    print("\n🔧 Checking system requirements...")
    
    # Check components
    browser_ok = check_browser()
    tor_ok = check_tor()
    warp_ok = check_warp()
    
    print("\n📊 Installation Summary:")
    print(f"✅ Dependencies: Installed")
    print(f"{'✅' if browser_ok else '⚠️'} Browser: {'Available' if browser_ok else 'Not found'}")
    print(f"{'✅' if tor_ok else '⚠️'} TOR: {'Running' if tor_ok else 'Not running'}")
    print(f"{'✅' if warp_ok else '⚠️'} WARP: {'Connected' if warp_ok else 'Not connected'}")
    
    if browser_ok or tor_ok or warp_ok:
        print("\n🎉 Parser is ready to use!")
        print("\nTo run the parser:")
        print("  python main.py")
        print("\nTo test components:")
        print("  python test_parser.py")
    else:
        print("\n⚠️ Parser may not work without browsers or proxies.")
        print("   Install at least one browser for basic functionality.")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
