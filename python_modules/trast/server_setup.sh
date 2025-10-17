#!/bin/bash

# Trast Parser - Server Deployment Script
# Quick setup and run for Linux servers

echo "🚀 Trast Parser - Server Setup"
echo "================================"

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.8+"
    exit 1
fi

echo "✅ Python 3 found: $(python3 --version)"

# Install system dependencies (if needed)
echo "📦 Checking system dependencies..."

# Check for Chrome/Chromium
if ! command -v google-chrome &> /dev/null && ! command -v chromium-browser &> /dev/null; then
    echo "⚠️ Chrome/Chromium not found. Installing..."
    
    # Detect OS and install Chrome
    if [ -f /etc/debian_version ]; then
        # Debian/Ubuntu
        wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
        echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
        sudo apt update
        sudo apt install -y google-chrome-stable
    elif [ -f /etc/redhat-release ]; then
        # CentOS/RHEL
        sudo yum install -y google-chrome-stable
    else
        echo "⚠️ Unknown OS. Please install Chrome manually."
    fi
else
    echo "✅ Chrome/Chromium found"
fi

# Install Python dependencies
echo "📦 Installing Python dependencies..."
python3 -m pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo "❌ Failed to install Python dependencies"
    exit 1
fi

echo "✅ Python dependencies installed"

# Test components
echo "🧪 Testing components..."
python3 test_parser.py

if [ $? -ne 0 ]; then
    echo "⚠️ Component test failed, but continuing..."
fi

# Run parser
echo "🎯 Running Trast parser..."
python3 main.py

if [ $? -eq 0 ]; then
    echo "🎉 Parser completed successfully!"
else
    echo "❌ Parser failed"
    exit 1
fi

echo "✅ All done!"
