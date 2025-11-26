# HexGlitcher - Raw Hex Image Databender

A production-ready image glitching tool that manipulates raw byte data while preserving file headers to maintain validity. Create stunning glitch art by corrupting images at the hex level with surgical precision or chaotic randomness.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)

## Features

- **Header Protection:** Adjustable "Safe Zone" to protect file headers (e.g., first 500 bytes) from corruption
- **Hex Preview:** View the raw hex data of your image in real-time
- **Find & Replace:** Target specific byte sequences (e.g., replace all `FF` with `00`) for structured glitching
- **Random Glitch:** Randomly modify bytes with multiple algorithms (Random, Increment, XOR, etc.)
- **Real-time Preview:** See the results instantly with automatic preview updates
- **Production-Ready:** Comprehensive input validation, error handling, and security hardening

## Download

### Pre-built Executables (Recommended)

Download the latest release for your platform - no Python installation required:

**[📥 Download Latest Release](https://github.com/willbearfruits/hexglitcher/releases/latest)**

- **Windows:** `HexGlitcher-Windows-Portable.zip` - Portable EXE (no installation)
- **Linux:** `HexGlitcher-x86_64.AppImage` - Universal AppImage
- **macOS:** `HexGlitcher-macOS.dmg` - Disk image installer

### Quick Start (Executables)

**Windows:**
1. Download and extract `HexGlitcher-Windows-Portable.zip`
2. Run `HexGlitcher.exe`

**Linux:**
```bash
chmod +x HexGlitcher-x86_64.AppImage
./HexGlitcher-x86_64.AppImage
```

**macOS:**
1. Open `HexGlitcher-macOS.dmg`
2. Drag `HexGlitcher.app` to Applications
3. Right-click → Open (first time only)

## Installation from Source

### Requirements
- Python 3.8 or higher
- Tkinter (usually included with Python)

### Install with pip

```bash
# Clone the repository
git clone https://github.com/willbearfruits/hexglitcher.git
cd hexglitcher

# Install dependencies
pip install -r requirements.txt
```

### Run from Source

```bash
python main.py
```

Or use the convenience script:
```bash
./run.sh  # Linux/macOS
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

### File Format Guidance

- **JPEG (JPG):** Very sensitive to corruption. Small changes can cause massive visual shifts
  - Keep "Intensity" high (1 change per 5000+ bytes)
  - Header protection around 600-800 bytes
  - Start conservative and increase corruption gradually

- **BMP:** Very stable and predictable
  - Can use aggressive glitch settings
  - Great for learning and experimentation
  - Low header protection (200-400 bytes) usually sufficient

- **PNG:** Uses checksums (CRC) for integrity checking
  - Some viewers will reject corrupted PNGs
  - Most browsers handle minor corruption gracefully
  - Try increasing header protection if it breaks completely
  - Glitch gently or specifically target non-critical chunks

- **GIF:** Animation frames can be individually corrupted
  - Moderate sensitivity
  - Interesting results with find/replace on color tables

- **WebP:** Modern format with good corruption tolerance
  - Similar behavior to PNG
  - Header protection around 500-700 bytes

## Security Features

HexGlitcher includes production-grade security hardening:

- ✓ File size validation (100MB limit)
- ✓ File type validation (images only)
- ✓ Integer input validation
- ✓ Hex input validation
- ✓ Path traversal protection
- ✓ System directory write protection
- ✓ Comprehensive error handling
- ✓ Logging system for debugging

## Building from Source

Want to build your own executables? See [BUILDING.md](BUILDING.md) for detailed instructions.

### Quick Build

```bash
# Install build dependencies
pip install -r requirements-build.txt

# Build for your platform
python build.py
```

Outputs will be in the `dist/` directory.

## Development

### Project Structure

```
image-glitcher/
├── main.py              # Main application code
├── hexglitcher.spec     # PyInstaller configuration
├── build.py             # Cross-platform build script
├── requirements.txt     # Runtime dependencies
├── requirements-build.txt  # Build dependencies
├── README.md            # This file
├── BUILDING.md          # Build instructions
├── LICENSE              # MIT License
└── .github/
    └── workflows/
        └── build-release.yml  # Automated builds
```

### Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs and feature requests.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Credits

Created with [Claude Code](https://claude.com/claude-code)

## Changelog

### v1.0.0 (Initial Release)

- Production-ready image glitching tool
- Windows, Linux, and macOS support
- Comprehensive security hardening
- Real-time preview and hex display
- Multiple glitch algorithms
- Header protection mechanism
- Find & replace functionality
- Logging system

## Support

- **Issues:** Report bugs and request features on [GitHub Issues](https://github.com/willbearfruits/hexglitcher/issues)
- **Documentation:** See [BUILDING.md](BUILDING.md) for build instructions
- **License:** MIT (see [LICENSE](LICENSE))

## Acknowledgments

- Built with [Pillow](https://python-pillow.org/) for image processing
- Uses [PyInstaller](https://pyinstaller.org/) for executable creation
- GUI built with [Tkinter](https://docs.python.org/3/library/tkinter.html)
