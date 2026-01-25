#!/bin/bash

set -eo pipefail

if [[ ! $1 =~ ^(wifi|serial)$ ]]
then
    echo 1>&2 "usage: $0 <serial | wifi>"
    exit 1
fi
mode=$1

cat <<EOF
Make sure that MicroPython v1.26 or newer is installed on the
Raspberry Pi Pico and that it is waiting on the Python repl.
EOF

mpremote cp src/*.py :
mpremote cp src/main_${mode}.py :main.py
mpremote reset
