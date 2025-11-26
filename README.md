# HexGlitcher - Python Image Databender

A raw hex-level image glitching tool that allows for data bending while preserving file headers to maintain file validity.

## Features
- **Header Protection:** Adjustable "Safe Zone" to protect file headers (e.g., first 500 bytes) from corruption.
- **Hex Preview:** View the raw hex data of your image.
- **Find & Replace:** Target specific byte sequences (e.g., replace all `FF` with `00`) for structured glitching.
- **Random Glitch:** randomly modify bytes with various algorithms (Random, Increment, XOR, etc.).
- **Real-time Preview:** See the results instantly. If the file breaks, the tool warns you.

## Installation

1. Ensure you have Python installed.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Run the tool:
   ```bash
   python main.py
   ```
2. Click **Load Image** to select a file (JPG, PNG, BMP, GIF, etc.).
3. Adjust **Header Protection** if the file breaks immediately (Try increasing to 1000+ for complex PNGs).
4. Use **Find & Replace** or **Random Corruption** to glitch the image.
5. Click **Save Result** when satisfied.

## Tips
- **Compressed Files (JPG):** Very sensitive. Small changes can cause massive shifts. Keep "Intensity" high (meaning 1 change per many bytes, e.g., 1/5000) and header protection around 600+.
- **Uncompressed (BMP):** Very stable. You can be aggressive with glitches.
- **PNG:** Often uses checksums (CRC). Glitching might render it unreadable by some strict viewers, but standard browsers often handle it. If it breaks, try finding the CRC chunks or just use the random glitcher gently.
