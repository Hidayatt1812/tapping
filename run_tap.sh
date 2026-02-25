#!/usr/bin/env bash
set -e

# one port logger
python3 tap_logger_multiport.py --port /dev/ttyS3@19200 --out tap.txt

# two port logger
# python3 tap_logger_multiport.py \
#   --port FCC=/dev/ttyS3@57600 \
#   --port PTS=/dev/ttyS4@19200 \
#   --out tap.txt

# three port logger
# python3 tap_logger_multiport.py \
#   --port TAP1=/dev/ttyS3@57600 \
#   --port TAP2=/dev/ttyS4@19200 \
#   --port TAP3=/dev/ttyS5@19200 \
#   --out tap.txt