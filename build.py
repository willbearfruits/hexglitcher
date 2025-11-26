#!/usr/bin/env python3
"""
HexGlitcher Build Script
Builds standalone executables for Windows, Linux, and macOS
"""

import sys
import os
import subprocess
import shutil
import platform
from pathlib import Path

# Fix Windows console encoding for Unicode characters
if sys.platform == 'win32':
    try:
        # Try to set UTF-8 encoding for Windows console
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        # Python < 3.7 fallback
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

# Colors for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_step(message):
    """Print a build step message."""
    print(f"{Colors.OKBLUE}{Colors.BOLD}>>> {message}{Colors.ENDC}")

def print_success(message):
    """Print a success message."""
    # Use ASCII checkmark on Windows if Unicode fails
    checkmark = "√" if sys.platform != 'win32' else "[OK]"
    print(f"{Colors.OKGREEN}{checkmark} {message}{Colors.ENDC}")

def print_error(message):
    """Print an error message."""
    # Use ASCII X on Windows if Unicode fails
    xmark = "✗" if sys.platform != 'win32' else "[ERROR]"
    print(f"{Colors.FAIL}{xmark} {message}{Colors.ENDC}")

def print_warning(message):
    """Print a warning message."""
    # Use ASCII warning on Windows if Unicode fails
    warning = "⚠" if sys.platform != 'win32' else "[WARN]"
    print(f"{Colors.WARNING}{warning} {message}{Colors.ENDC}")

def check_dependencies():
    """Check if required build dependencies are installed."""
    print_step("Checking dependencies...")

    try:
        import PyInstaller
        print_success(f"PyInstaller {PyInstaller.__version__} found")
    except ImportError:
        print_error("PyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print_success("PyInstaller installed")

    try:
        import PIL
        print_success(f"Pillow {PIL.__version__} found")
    except ImportError:
        print_error("Pillow not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow>=11.0.0"])
        print_success("Pillow installed")

def clean_build_dirs():
    """Clean previous build artifacts."""
    print_step("Cleaning previous build artifacts...")

    dirs_to_clean = ['build', 'dist', '__pycache__']
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)
            print_success(f"Removed {dir_name}/")

    # Remove spec file if it exists (we'll use our custom one)
    if os.path.exists('main.spec'):
        os.remove('main.spec')
        print_success("Removed old spec file")

def build_executable():
    """Build the executable using PyInstaller."""
    print_step("Building executable with PyInstaller...")

    system = platform.system()
    print(f"Building for: {system}")

    try:
        subprocess.check_call([
            sys.executable,
            "-m", "PyInstaller",
            "--clean",
            "--noconfirm",
            "hexglitcher.spec"
        ])
        print_success("Build completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Build failed: {e}")
        return False

def create_linux_appimage():
    """Create Linux AppImage (requires appimagetool)."""
    print_step("Creating Linux AppImage...")

    if platform.system() != "Linux":
        print_warning("Skipping AppImage creation (not on Linux)")
        return False

    # Check if appimagetool is available
    if not shutil.which("appimagetool"):
        print_warning("appimagetool not found. Install with:")
        print("  wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage")
        print("  chmod +x appimagetool-x86_64.AppImage")
        print("  sudo mv appimagetool-x86_64.AppImage /usr/local/bin/appimagetool")
        return False

    # Create AppDir structure
    appdir = Path("HexGlitcher.AppDir")
    if appdir.exists():
        shutil.rmtree(appdir)

    appdir.mkdir()
    (appdir / "usr").mkdir()
    (appdir / "usr" / "bin").mkdir(parents=True)

    # Copy executable
    shutil.copy("dist/HexGlitcher", appdir / "usr" / "bin" / "HexGlitcher")

    # Create .desktop file
    desktop_content = """[Desktop Entry]
Name=HexGlitcher
Exec=HexGlitcher
Icon=hexglitcher
Type=Application
Categories=Graphics;
Comment=Raw hex-level image glitching tool
"""
    (appdir / "hexglitcher.desktop").write_text(desktop_content)

    # Create AppRun script
    apprun_content = """#!/bin/bash
SELF=$(readlink -f "$0")
HERE=${SELF%/*}
export PATH="${HERE}/usr/bin/:${PATH}"
export LD_LIBRARY_PATH="${HERE}/usr/lib/:${LD_LIBRARY_PATH}"
exec "${HERE}/usr/bin/HexGlitcher" "$@"
"""
    apprun_path = appdir / "AppRun"
    apprun_path.write_text(apprun_content)
    apprun_path.chmod(0o755)

    # Create icon (placeholder - would need actual icon)
    print_warning("Note: Add icon.png to project root for proper AppImage icon")

    # Build AppImage
    try:
        subprocess.check_call(["appimagetool", str(appdir), "dist/HexGlitcher-x86_64.AppImage"])
        print_success("AppImage created: dist/HexGlitcher-x86_64.AppImage")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"AppImage creation failed: {e}")
        return False

def create_macos_dmg():
    """Create macOS DMG installer."""
    print_step("Creating macOS DMG...")

    if platform.system() != "Darwin":
        print_warning("Skipping DMG creation (not on macOS)")
        return False

    app_bundle = "dist/HexGlitcher.app"
    if not os.path.exists(app_bundle):
        print_error(f"App bundle not found: {app_bundle}")
        return False

    dmg_name = "dist/HexGlitcher-macOS.dmg"

    # Remove old DMG if exists
    if os.path.exists(dmg_name):
        os.remove(dmg_name)

    try:
        subprocess.check_call([
            "hdiutil", "create",
            "-volname", "HexGlitcher",
            "-srcfolder", app_bundle,
            "-ov",
            "-format", "UDZO",
            dmg_name
        ])
        print_success(f"DMG created: {dmg_name}")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"DMG creation failed: {e}")
        return False

def create_windows_portable():
    """Create Windows portable zip."""
    print_step("Creating Windows portable package...")

    if platform.system() != "Windows":
        print_warning("Note: Building for Windows from non-Windows system")

    exe_path = "dist/HexGlitcher.exe"
    if not os.path.exists(exe_path):
        print_error(f"Executable not found: {exe_path}")
        return False

    # Create portable package directory
    portable_dir = Path("dist/HexGlitcher-Windows-Portable")
    if portable_dir.exists():
        shutil.rmtree(portable_dir)
    portable_dir.mkdir(parents=True)

    # Copy executable
    shutil.copy(exe_path, portable_dir / "HexGlitcher.exe")

    # Copy README
    if os.path.exists("README.md"):
        shutil.copy("README.md", portable_dir / "README.md")

    # Copy LICENSE
    if os.path.exists("LICENSE"):
        shutil.copy("LICENSE", portable_dir / "LICENSE.txt")

    # Create portable info file
    portable_info = portable_dir / "PORTABLE_INFO.txt"
    portable_info.write_text("""HexGlitcher - Portable Edition

This is a portable version of HexGlitcher.
No installation required - just run HexGlitcher.exe

Features:
- No admin rights needed
- Runs from any folder
- Leaves no registry entries
- Can run from USB drive

For more information, see README.md
""")

    # Create zip archive
    zip_name = "dist/HexGlitcher-Windows-Portable"
    shutil.make_archive(zip_name, 'zip', portable_dir)
    print_success(f"Portable package created: {zip_name}.zip")

    return True

def display_results():
    """Display build results."""
    print()
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}Build Results{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print()

    dist_path = Path("dist")
    if dist_path.exists():
        files = list(dist_path.iterdir())
        if files:
            print("Created files:")
            for file in sorted(files):
                size = file.stat().st_size if file.is_file() else 0
                size_mb = size / (1024 * 1024)
                if file.is_file():
                    print(f"  {Colors.OKGREEN}▸{Colors.ENDC} {file.name} ({size_mb:.1f} MB)")
                elif file.is_dir() and file.suffix != '.app':
                    print(f"  {Colors.OKGREEN}▸{Colors.ENDC} {file.name}/ (directory)")
        else:
            print_warning("No files created in dist/")
    else:
        print_warning("dist/ directory not found")

    print()
    print(f"{Colors.OKBLUE}Next steps:{Colors.ENDC}")
    print("  1. Test the executable in dist/")
    print("  2. Create a GitHub release")
    print("  3. Upload the distributables")
    print()

def main():
    """Main build process."""
    print()
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}HexGlitcher Build Script{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print()

    # Check dependencies
    check_dependencies()

    # Clean previous builds
    clean_build_dirs()

    # Build executable
    if not build_executable():
        print_error("Build failed. Exiting.")
        sys.exit(1)

    # Platform-specific packaging
    system = platform.system()

    if system == "Linux":
        create_linux_appimage()
        print_success("Linux build completed")
    elif system == "Darwin":
        create_macos_dmg()
        print_success("macOS build completed")
    elif system == "Windows":
        create_windows_portable()
        print_success("Windows build completed")
    else:
        print_warning(f"Unknown platform: {system}")

    # Display results
    display_results()

    print_success("Build process completed!")

if __name__ == "__main__":
    main()
