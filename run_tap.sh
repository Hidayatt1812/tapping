#!/usr/bin/env bash
set -e

# GANTI INI sesuai port kamu di WSL1:
FPORT="/dev/ttyS3"   # RS232 (FCC <-> PTS) TAP OUTPUT
PPORT="/dev/ttyS4"   # RS485 (PTS <-> Dispenser) TAP OUTPUT

python3 tap.py \
  --fport "$FPORT" --pport "$PPORT" \
  --baud-f 57600 --baud-p 19200 \
  --out log_tap.txt \
  --mode hex