#!/bin/sh

set -e

mpremote reset
sleep 1
mpremote cp *.py :
mpremote exec "import main"
mpremote repl
