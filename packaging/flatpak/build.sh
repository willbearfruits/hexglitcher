#!/usr/bin/env bash
# Build, install (per-user), and bundle the HexGlitcher Flatpak.
#
# Requires: flatpak + org.flatpak.Builder + org.kde.Platform//6.9 + org.kde.Sdk//6.9
#   flatpak install --user flathub org.flatpak.Builder org.kde.Platform//6.9 org.kde.Sdk//6.9
set -euo pipefail
APP=io.github.willbearfruits.HexGlitcher
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

# Build, export to a local repo, and install for the current user.
flatpak run org.flatpak.Builder --force-clean --user --install \
    --repo=_repo build-dir "$APP.yml"

# Single-file bundle for distribution / GitHub release.
flatpak build-bundle _repo HexGlitcher.flatpak "$APP"

echo
echo "Built:  $HERE/HexGlitcher.flatpak"
echo "Run:    flatpak run $APP"
