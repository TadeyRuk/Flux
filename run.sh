#!/bin/bash
cd "$(dirname "$0")/src"
exec python3 main.py "$@"
