#!/usr/bin/env bash
set -euo pipefail

# Run ExifTool from our repo bundle.
# We call "perl exiftool" so we don't need the system exiftool binary.

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXIF="$DIR/exiftool"

if [ ! -f "$EXIF" ]; then
  echo "ERROR: bundled exiftool not found at $EXIF" >&2
  exit 2
fi

exec perl "$EXIF" "$@"
