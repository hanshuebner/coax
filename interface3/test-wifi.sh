#!/bin/sh

set -e

mpremote reset
sleep 3
mpremote cp src/*.py :
mpremote exec "import main_wifi"
mpremote repl
