How to add ExifTool to this repo:

1) Download ExifTool (the "exiftool" script) from the official distribution.
2) Put the "exiftool" file into this folder (bin/exiftool/exiftool).
3) Commit it.

We run it via:
  perl bin/exiftool/exiftool ...

This avoids apt-get and Docker on Render.
