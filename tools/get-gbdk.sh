#!/bin/sh
# Download GBDK-2020 into tools/gbdk (the Makefile picks it up automatically).
# Linux (x86-64, arm64) and macOS (Intel, Apple Silicon). On Arch Linux you
# can use the gbdk-2020 AUR package instead.
set -eu

VERSION=4.5.0
DEST="$(cd "$(dirname "$0")" && pwd)/gbdk"
STAMP="$DEST/.pandajump-gbdk-version"

case "$(uname -s)-$(uname -m)" in
  Linux-x86_64)
    PKG=gbdk-linux64.tar.gz
    SHA256=d7857a5f6d135ee4c249043ca26aad9f2ec8ab5d4106d97720d404114f42605c ;;
  Linux-aarch64|Linux-arm64)
    PKG=gbdk-linux-arm64.tar.gz
    SHA256=31eb2235f0fdb60163d0b1e9574a022098d6069cd56606a1daca4478a46e0439 ;;
  Darwin-arm64)
    PKG=gbdk-macos-arm64.tar.gz
    SHA256=289ee60e46c5a2785a21e35533f84a5131ed4a063b21b0dbdedc9a10af15bf78 ;;
  Darwin-x86_64)
    PKG=gbdk-macos.tar.gz
    SHA256=1aa549d12032d8f6509d11923bb28b1a453098f42597feb378e9a42541f8fd89 ;;
  *)
    echo "No prebuilt GBDK-2020 for $(uname -s)-$(uname -m)." >&2
    echo "See https://github.com/gbdk-2020/gbdk-2020/releases, then run: make GBDK_HOME=/path/to/gbdk/" >&2
    exit 1 ;;
esac

if [ -x "$DEST/bin/lcc" ] && [ "$(cat "$STAMP" 2>/dev/null)" = "$VERSION" ]; then
  echo "GBDK-2020 $VERSION is already installed in $DEST"
  exit 0
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
URL="https://github.com/gbdk-2020/gbdk-2020/releases/download/$VERSION/$PKG"
echo "Downloading $URL"
curl -fsSL -o "$TMP/$PKG" "$URL"

if command -v sha256sum >/dev/null 2>&1; then
  echo "$SHA256  $TMP/$PKG" | sha256sum -c -
else
  echo "$SHA256  $TMP/$PKG" | shasum -a 256 -c -
fi

tar -xzf "$TMP/$PKG" -C "$TMP"
rm -rf "$DEST"
mv "$TMP/gbdk" "$DEST"
echo "$VERSION" > "$STAMP"
echo "Installed GBDK-2020 $VERSION in $DEST"
