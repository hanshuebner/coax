#!/bin/sh
#
# Link the coax capture plugin and dissector into Wireshark's personal
# plugin folders, so the interface shows up in the capture list and
# captured frames are decoded.

set -e

here=$(cd "$(dirname "$0")" && pwd)

tshark=$(command -v tshark || true)
if [ -z "$tshark" ] && [ -x /Applications/Wireshark.app/Contents/MacOS/tshark ]; then
    tshark=/Applications/Wireshark.app/Contents/MacOS/tshark
fi
if [ -z "$tshark" ]; then
    echo "tshark not found; install Wireshark first" >&2
    exit 1
fi

folders=$("$tshark" -G folders 2>/dev/null)
extcap_dir=$(echo "$folders" | awk -F'\t' '/^Personal Extcap path:/ { print $2 }')
lua_dir=$(echo "$folders" | awk -F'\t' '/^Personal Lua Plugins:/ { print $2 }')

if [ -z "$extcap_dir" ] || [ -z "$lua_dir" ]; then
    echo "could not determine Wireshark plugin folders" >&2
    exit 1
fi

mkdir -p "$extcap_dir" "$lua_dir"
ln -sf "$here/coax-capture" "$extcap_dir/coax-capture"
ln -sf "$here/coax.lua" "$lua_dir/coax.lua"

echo "capture plugin: $extcap_dir/coax-capture"
echo "dissector:      $lua_dir/coax.lua"
echo
echo "Restart Wireshark to pick them up."
