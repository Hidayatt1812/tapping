#!/usr/bin/env bash
set -e


FPORT="/dev/ttyS3"   
PPORT="/dev/ttyS4"   

python3 tap.py \
  --fport "/dev/ttyACM1" --pport "/dev/ttyACM1" \
  --baud-f 9600 --baud-p 9600 \
  --out log_tap.txt \
  --mode hex