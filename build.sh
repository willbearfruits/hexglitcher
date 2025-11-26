#!/bin/bash
# HexGlitcher Build Script for Linux/macOS

set -e

echo "========================================"
echo "HexGlitcher Build Script"
echo "========================================"
echo ""

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    exit 1
fi

# Run the build script
python3 build.py

echo ""
echo "Build complete! Check the dist/ folder for output."
