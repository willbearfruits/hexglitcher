# Building HexGlitcher

This document describes how to build standalone executables for HexGlitcher on Windows, Linux, and macOS.

## Quick Start

### Prerequisites

- Python 3.8 or higher
- pip (Python package installer)
- Git

### Building on Your Platform

**Linux / macOS:**
```bash
./build.sh
```

**Windows:**
```cmd
build.bat
```

**Any platform (using Python directly):**
```bash
python build.py
```

The build script will:
1. Check and install dependencies (PyInstaller, Pillow)
2. Clean previous build artifacts
3. Build the executable using PyInstaller
4. Create platform-specific packages

## Platform-Specific Instructions

### Windows (EXE + Portable ZIP)

**Requirements:**
- Windows 10 or later
- Python 3.8+

**Build Steps:**
```cmd
# Install build dependencies
pip install -r requirements-build.txt

# Run build
build.bat
```

**Output:**
- `dist/HexGlitcher.exe` - Standalone executable
- `dist/HexGlitcher-Windows-Portable.zip` - Portable package with README and LICENSE

**Notes:**
- The executable is fully standalone - no installation required
- Can be run from USB drives or any folder
- No admin rights needed
- Includes all Python dependencies bundled

### Linux (Binary + AppImage)

**Requirements:**
- Linux (tested on Ubuntu 22.04, Mint 21.3)
- Python 3.8+
- `python3-tk` package
- `appimagetool` (for AppImage creation)

**Build Steps:**
```bash
# Install system dependencies
sudo apt-get install python3-tk libfuse2

# Install build dependencies
pip install -r requirements-build.txt

# Download appimagetool
wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
chmod +x appimagetool-x86_64.AppImage
sudo mv appimagetool-x86_64.AppImage /usr/local/bin/appimagetool

# Run build
./build.sh
```

**Output:**
- `dist/HexGlitcher` - Standalone binary
- `dist/HexGlitcher-x86_64.AppImage` - AppImage (if appimagetool is installed)

**Notes:**
- AppImage works on most modern Linux distributions
- No installation required - just make executable and run
- If appimagetool is not available, you'll still get the standalone binary

### macOS (APP + DMG)

**Requirements:**
- macOS 10.13 or later
- Python 3.8+
- Xcode Command Line Tools

**Build Steps:**
```bash
# Install Xcode Command Line Tools (if not already installed)
xcode-select --install

# Install build dependencies
pip install -r requirements-build.txt

# Run build
./build.sh
```

**Output:**
- `dist/HexGlitcher.app` - macOS application bundle
- `dist/HexGlitcher-macOS.dmg` - Disk image installer

**Notes:**
- The .app bundle can be dragged to Applications folder
- DMG provides a convenient installer experience
- May need to right-click → Open first time to bypass Gatekeeper (unsigned app)

## Manual PyInstaller Build

If the automated build script doesn't work, you can build manually:

```bash
# Install PyInstaller
pip install pyinstaller

# Build using the spec file
pyinstaller --clean --noconfirm hexglitcher.spec
```

The executable will be in `dist/`.

## Build Configuration

### Customizing the Build

Edit `hexglitcher.spec` to customize:

- **Icon:** Replace `icon.ico` (Windows) or `icon.icns` (macOS)
- **App name:** Change the `name` parameter in `EXE()`
- **Console window:** Change `console=False` to `console=True` for debug builds
- **Compression:** Add `upx=True` for smaller executables (requires UPX)

### Adding an Icon

**Windows (.ico):**
```bash
# Create from PNG using ImageMagick
convert icon.png -define icon:auto-resize=256,128,64,48,32,16 icon.ico
```

**macOS (.icns):**
```bash
# Create from PNG
mkdir icon.iconset
sips -z 16 16     icon.png --out icon.iconset/icon_16x16.png
sips -z 32 32     icon.png --out icon.iconset/icon_16x16@2x.png
sips -z 32 32     icon.png --out icon.iconset/icon_32x32.png
sips -z 64 64     icon.png --out icon.iconset/icon_32x32@2x.png
sips -z 128 128   icon.png --out icon.iconset/icon_128x128.png
sips -z 256 256   icon.png --out icon.iconset/icon_128x128@2x.png
sips -z 256 256   icon.png --out icon.iconset/icon_256x256.png
sips -z 512 512   icon.png --out icon.iconset/icon_256x256@2x.png
sips -z 512 512   icon.png --out icon.iconset/icon_512x512.png
sips -z 1024 1024 icon.png --out icon.iconset/icon_512x512@2x.png
iconutil -c icns icon.iconset
```

## GitHub Actions (Automated Releases)

The repository includes a GitHub Actions workflow that automatically builds releases for all platforms when you push a version tag.

### Creating a Release

```bash
# Tag your commit
git tag v1.0.0

# Push the tag to GitHub
git push origin v1.0.0
```

GitHub Actions will:
1. Build executables for Windows, Linux, and macOS
2. Create a GitHub Release
3. Upload all distributables as release assets

You can also trigger builds manually from the Actions tab in GitHub.

## Troubleshooting

### PyInstaller "Module not found" errors

If you get import errors when running the built executable:

1. Add the missing module to `hiddenimports` in `hexglitcher.spec`
2. Rebuild with `pyinstaller --clean hexglitcher.spec`

### Tkinter not found

**Linux:**
```bash
sudo apt-get install python3-tk
```

**macOS:**
Tkinter should be included with Python from python.org. If using Homebrew:
```bash
brew install python-tk
```

**Windows:**
Reinstall Python and ensure "tcl/tk and IDLE" is checked during installation.

### Large Executable Size

To reduce executable size:

1. Install UPX: https://upx.github.io/
2. Set `upx=True` in `hexglitcher.spec`
3. Rebuild

### AppImage won't run

Make sure you have FUSE installed:
```bash
sudo apt-get install libfuse2
```

Or run the AppImage in extracted mode:
```bash
./HexGlitcher-x86_64.AppImage --appimage-extract-and-run
```

### macOS "App is damaged" message

This happens with unsigned apps. To run:
1. Right-click the app
2. Select "Open"
3. Click "Open" in the dialog

Or remove the quarantine attribute:
```bash
xattr -cr HexGlitcher.app
```

## Cross-Platform Building

While the build scripts work best on their native platforms, you can cross-compile:

### Building for Windows from Linux/macOS

Use Wine with PyInstaller:
```bash
pip install pyinstaller[windows]
pyinstaller --platform win32 hexglitcher.spec
```

Note: This is experimental and may have issues with Tkinter.

### Building for Linux from macOS/Windows

This is not officially supported. Use Docker or a Linux VM:
```bash
docker run --rm -v $(pwd):/work ubuntu:22.04 bash -c "
    apt-get update &&
    apt-get install -y python3 python3-pip python3-tk &&
    cd /work &&
    pip3 install -r requirements-build.txt &&
    python3 build.py
"
```

## Testing the Build

After building, test the executable:

1. **Run without Python:** Move/copy the executable to a different machine without Python installed
2. **Test all features:**
   - Load an image
   - Apply hex find/replace
   - Apply random glitch
   - Save the result
3. **Check logs:** Look for `hexglitcher.log` for any errors
4. **Test edge cases:**
   - Large files (near 100MB limit)
   - Invalid inputs
   - Corrupted images

## Release Checklist

Before creating a release:

- [ ] Version number updated in code
- [ ] All tests pass
- [ ] Build succeeds on all platforms
- [ ] README.md is up to date
- [ ] CHANGELOG.md is updated
- [ ] LICENSE is correct
- [ ] Icons are present (optional but recommended)
- [ ] Executables tested on target platforms

## Additional Resources

- [PyInstaller Documentation](https://pyinstaller.org/)
- [AppImage Documentation](https://docs.appimage.org/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)

## Getting Help

If you encounter build issues:

1. Check the [Troubleshooting](#troubleshooting) section
2. Search existing GitHub issues
3. Create a new issue with:
   - Your platform and Python version
   - Full build output/error messages
   - Steps to reproduce
