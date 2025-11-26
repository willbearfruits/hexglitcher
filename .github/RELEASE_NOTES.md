# 🎨 HexGlitcher v1.0.0 - Production Release

**Transform images into stunning glitch art with surgical precision!**

HexGlitcher is a production-ready tool for creating glitch art by manipulating raw byte data in image files. Perfect for artists, designers, and anyone who wants to explore the aesthetic possibilities of controlled corruption.

---

## ✨ What is HexGlitcher?

HexGlitcher lets you corrupt images at the hex (byte) level while protecting critical file headers to keep files valid. Think of it as a controlled demolition tool for your images - you get all the beautiful chaos of glitch art without completely destroying the file.

### 🎯 Key Features

- **🛡️ Header Protection** - Adjustable "safe zone" keeps your files valid while corrupting the rest
- **👁️ Real-time Preview** - See your glitches instantly as you create them
- **🔍 Hex Viewer** - Peek at the raw byte data you're manipulating
- **🎲 Multiple Glitch Modes** - Random, Increment, Decrement, Zero, XOR operations
- **🔎 Find & Replace** - Target specific byte sequences for surgical glitching
- **🔒 Production-Ready Security** - Input validation, size limits, path protection

---

## 📥 Download & Install

### Quick Start (No Python Required!)

Choose your platform and download:

| Platform | File | Size | Instructions |
|----------|------|------|--------------|
| 🪟 **Windows** | `HexGlitcher-Windows-Portable.zip` | ~25 MB | Extract and run `HexGlitcher.exe` |
| 🐧 **Linux** | `HexGlitcher-x86_64.AppImage` | ~45 MB | `chmod +x` and run |
| 🍎 **macOS** | `HexGlitcher-macOS.dmg` | ~35 MB | Open DMG, drag to Applications |

**No installation, no admin rights, no Python needed!** Just download and run.

### Installation Instructions

**Windows:**
1. Download `HexGlitcher-Windows-Portable.zip`
2. Extract the ZIP file anywhere you like
3. Double-click `HexGlitcher.exe`
4. Start glitching!

**Linux:**
```bash
# Download the AppImage
wget https://github.com/willbearfruits/hexglitcher/releases/download/v1.0.0/HexGlitcher-x86_64.AppImage

# Make it executable
chmod +x HexGlitcher-x86_64.AppImage

# Run it
./HexGlitcher-x86_64.AppImage
```

**macOS:**
1. Download `HexGlitcher-macOS.dmg`
2. Open the DMG file
3. Drag HexGlitcher.app to your Applications folder
4. Right-click the app and select "Open" (first time only)
5. Click "Open" in the security dialog

---

## 🚀 Quick Usage Guide

1. **Load an Image** - Click "Load Image" and select any JPG, PNG, BMP, GIF, or WebP
2. **Set Header Protection** - Start with 500 bytes (increase for complex files like PNG)
3. **Choose Your Glitch:**
   - **Find & Replace:** Target specific byte patterns (try replacing `FF` with `00`)
   - **Random Glitch:** Set intensity and pick an operation mode
4. **Preview** - See results instantly in the preview pane
5. **Save** - Click "Save Result" when you love what you see!

### 💡 Pro Tips

**For Different File Types:**
- **JPEG:** Very sensitive - use high intensity (1/5000+) and 600+ header protection
- **BMP:** Very stable - go wild with aggressive settings!
- **PNG:** Uses checksums - glitch gently or increase header protection to 1000+
- **GIF:** Great for corrupting animation frames - moderate settings work well

**Creative Techniques:**
- Replace color bytes for palette shifts
- Use XOR mode for inverted color effects
- Target specific byte values for structured glitches
- Combine find/replace with random glitching
- Experiment with different header sizes for varied effects

---

## 🔒 Security & Quality

This is a **production-ready** release with enterprise-grade security:

- ✅ File size validation (100MB max)
- ✅ File type validation (images only)
- ✅ Input validation on all user inputs
- ✅ Path traversal protection
- ✅ System directory write protection
- ✅ Comprehensive error handling
- ✅ Logging system for debugging

**Dependencies:**
- Pillow 11.0.0+ (latest security patches applied)
- All known CVEs patched

---

## 📝 Changelog

### What's New in v1.0.0

**Core Features:**
- Production-ready image glitching with GUI
- Header protection mechanism to preserve file validity
- Real-time preview with hex data display
- Find & replace for specific byte sequences
- Random corruption with 5 different algorithms
- Support for JPEG, PNG, BMP, GIF, and WebP formats

**Security Improvements:**
- File size validation (100MB limit prevents memory exhaustion)
- File type validation (images only)
- Integer input validation with range checking
- Enhanced hex input validation
- Path traversal protection on save operations
- System directory write protection

**Code Quality:**
- Type hints on all methods
- Comprehensive docstrings
- Modular refactored architecture
- Optimized random glitch algorithm
- Constants extracted from magic numbers
- Comprehensive logging system

**Build System:**
- Cross-platform build scripts (Windows, Linux, macOS)
- Automated GitHub Actions CI/CD
- One-click builds for all platforms
- Portable executables with no dependencies

**Documentation:**
- Complete user guide in README
- Build instructions for developers
- Security feature documentation
- File format-specific tips and tricks

---

## 🛠️ Technical Details

**Built With:**
- **Language:** Python 3.8+
- **GUI Framework:** Tkinter (cross-platform)
- **Image Processing:** Pillow 11.0.0
- **Build Tool:** PyInstaller 6.0+
- **CI/CD:** GitHub Actions

**System Requirements:**
- **Windows:** 10 or later (64-bit)
- **Linux:** Any modern distribution (64-bit)
- **macOS:** 10.13 High Sierra or later
- **RAM:** 2GB minimum (4GB recommended)
- **Disk Space:** 100MB for app + working space for images

---

## 📚 Documentation

- **README:** [Full documentation and usage guide](https://github.com/willbearfruits/hexglitcher#readme)
- **Building:** [Build from source instructions](https://github.com/willbearfruits/hexglitcher/blob/master/BUILDING.md)
- **Issues:** [Report bugs or request features](https://github.com/willbearfruits/hexglitcher/issues)
- **License:** [MIT License](https://github.com/willbearfruits/hexglitcher/blob/master/LICENSE)

---

## 🤝 Contributing

This is an open-source project and contributions are welcome! Whether you're fixing bugs, adding features, or improving documentation, we'd love your help.

**Ways to Contribute:**
- 🐛 Report bugs via [GitHub Issues](https://github.com/willbearfruits/hexglitcher/issues)
- 💡 Suggest features or improvements
- 📖 Improve documentation
- 🔧 Submit pull requests with fixes or features
- ⭐ Star the repository if you find it useful!

---

## 📄 License

MIT License - Free to use, modify, and distribute. See [LICENSE](https://github.com/willbearfruits/hexglitcher/blob/master/LICENSE) for details.

---

## 🙏 Acknowledgments

Created with [Claude Code](https://claude.com/claude-code) 🤖

**Libraries Used:**
- [Pillow](https://python-pillow.org/) - The Python Imaging Library
- [Tkinter](https://docs.python.org/3/library/tkinter.html) - Python's standard GUI package
- [PyInstaller](https://pyinstaller.org/) - Freeze Python applications

---

## 🎨 Show Your Creations!

Made something cool with HexGlitcher? Share it with the community!

Tag your creations: `#HexGlitcher` `#GlitchArt`

---

**Enjoy creating beautiful chaos! 🎨✨**

*If you encounter any issues or have questions, please [open an issue](https://github.com/willbearfruits/hexglitcher/issues).*
