#!/bin/sh
# Download GBDK-2020 into tools/gbdk (the Makefile picks it up automatically).
# Linux x86-64 and macOS; on Arch you can use the gbdk-2020 AUR package instead.
set -eu

VERSION=4.5.0
DEST="$(cd "$(dirname "$0")" && pwd)/gbdk"

case "$(uname -s)-$(uname -m)" in
  Linux-x86_64) PKG=gbdk-linux64.tar.gz
                SHA256=d7857a5f6d135ee4c249043ca26aad9f2ec8ab5d4106d97720d404114f42605c ;;
  Darwin-arm64) PKG=gbdk-macos-arm64.tar.gz; SHA256= ;;
  Darwin-*)     PKG=gbdk-macos.tar.gz; SHA256= ;;
  *) echo "No prebuilt GBDK-2020 for $(uname -s)-$(uname -m); see https://github.com/gbdk-2020/gbdk-2020/releases" >&2; exit 1 ;;
esac

if [ -x "$DEST/bin/lcc" ]; then
  echo "GBDK-2020 already installed in $DEST"
  exit 0
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
URL="https://github.com/gbdk-2020/gbdk-2020/releases/download/$VERSION/$PKG"
echo "Downloading $URL"
curl -fsSL -o "$TMP/$PKG" "$URL"
if [ -n "$SHA256" ]; then
  echo "$SHA256  $TMP/$PKG" | sha256sum -c -
fi
tar -xzf "$TMP/$PKG" -C "$TMP"
mv "$TMP/gbdk" "$DEST"
echo "Installed GBDK-2020 $VERSION in $DEST"
