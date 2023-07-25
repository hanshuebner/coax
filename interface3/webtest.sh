#!/bin/sh

set -e

mpremote reset
sleep 1
mpremote cp rp_devices.py coax.py webserver.py wifi.py main.py :
mpremote exec "import main"
mpremote repl
