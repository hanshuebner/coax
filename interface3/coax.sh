#!/bin/sh

set -e

mpremote reset
sleep 1
mpremote cp coax.py :
mpremote exec "import coax"
mpremote repl
