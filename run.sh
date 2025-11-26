#!/bin/bash
# Checker for Tkinter and Pillow
if ! python3 -c "import tkinter" &> /dev/null; then
    echo "Error: tkinter is not installed. Please install it (e.g., sudo apt install python3-tk)"
    exit 1
fi

if ! python3 -c "import PIL" &> /dev/null; then
    echo "Pillow not found. Installing..."
    pip install -r requirements.txt
fi

python3 main.py