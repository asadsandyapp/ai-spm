#!/bin/sh
# Builds a production release and packages it into dist/ as a versioned
# tar.gz (the .deb + INSTALL-NOTES-LINUX.txt) - the Linux counterpart to
# scripts/package-release.ps1, so there's one command that always produces
# the same self-contained deliverable in the same place, reused by both
# local runs and the release workflow.
#
#   1. cargo build --release --workspace
#   2. cargo deb -p agent   (produces target/debian/ai-spm-dlp-agent_<version>_amd64.deb)
#   3. Copies the .deb and packaging/INSTALL-NOTES-LINUX.txt into dist/
#   4. tar.gz's them into dist/AI-SPM-DLP-Agent-linux-<version>.tar.gz
#
# dist/ is gitignored (it's build output); packaging/INSTALL-NOTES-LINUX.txt
# is the tracked, hand-maintained source of the usage notes bundled with
# every build - edit it there, not in dist/.

set -e

project_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$project_root"

echo "== Building release binaries =="
cargo build --release --workspace

echo "== Installing cargo-deb (if missing) =="
command -v cargo-deb >/dev/null 2>&1 || cargo install cargo-deb

echo "== Building the .deb (cargo deb) =="
cargo deb -p agent --no-build

deb="$(find "$project_root/target/debian" -maxdepth 1 -name '*.deb' | head -n 1)"
if [ -z "$deb" ]; then
    echo "no .deb found under target/debian after cargo deb" >&2
    exit 1
fi

version="$(sed -n 's/^version *= *"\([^"]*\)"/\1/p' "$project_root/Cargo.toml" | head -n 1)"

echo "== Assembling dist/ (version $version) =="
dist="$project_root/dist"
mkdir -p "$dist"
cp "$deb" "$dist/"
cp "$project_root/packaging/INSTALL-NOTES-LINUX.txt" "$dist/"

archive="$dist/AI-SPM-DLP-Agent-linux-$version.tar.gz"
rm -f "$archive"
tar -czf "$archive" -C "$dist" "$(basename "$deb")" "INSTALL-NOTES-LINUX.txt"

echo ""
echo "Done. Package: $archive"
ls -lh "$archive"
