# Serial Port Tapper v4.0 - Robust Edition

**Professional Serial Port Monitoring Tool dengan Smart TX/RX Detection**

Monitor komunikasi serial port (RS-232, RS-422, RS-485) secara real-time dengan detection pintar dan packet assembly otomatis.

[![Python Version](https://img.shields.io/badge/python-3.6+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-production-success.svg)]()

---

## 📋 Daftar Isi

- [Features](#-features)
- [Requirements](#-requirements)
- [Installation](#-installation)
- [Quick Start](#-quick-start)
- [Configuration](#️-configuration)
- [Detection Modes](#-detection-modes)
- [Protocol Support](#-protocol-support)
- [Background Mode](#️-background-mode)
- [Examples](#-examples)
- [Troubleshooting](#-troubleshooting)

---

## ✨ Features

### Core Features
✅ **Multi-Port Monitoring** - Monitor 1 atau lebih port bersamaan  
✅ **Per-Port Baudrate** - Setiap port bisa punya baudrate berbeda  
✅ **Smart TX/RX Detection** - Deteksi arah komunikasi otomatis  
✅ **Packet Assembly** - Gabung data fragmented otomatis  
✅ **Multi-Protocol** - RS-232, RS-422, RS-485 support  
✅ **Port Protection** - Auto stop jika port sedang dipakai  
✅ **Background Mode** - Jalankan sebagai daemon  
✅ **Real-time Monitoring** - Monitor data secara live  
✅ **Dynamic Logging** - Nama file dengan timestamp  
✅ **Colored Output** - Output berwarna untuk readability  

### Advanced Features
🎯 **Pattern Recognition** - Deteksi dari pattern (AT+, OK, GET)  
🎯 **Size Analysis** - Deteksi dari ukuran packet  
🎯 **RS-485 Specific** - Deteksi khusus Modbus/RS-485  
🎯 **Adaptive Learning** - Belajar dari history  
🎯 **Statistics** - Tracking TX/RX packets & bytes  
🎯 **Configurable Timeout** - Adjust packet timeout  

---

## 📦 Requirements

- **OS**: Linux (Ubuntu, Debian, Raspbian, dll)
- **Python**: 3.6+
- **Library**: pyserial

### Install Dependencies

```bash
pip3 install pyserial
```

### Set Permissions

```bash
sudo usermod -a -G dialout $USER
# Logout & login kembali
```

---

## Installation

```bash
# 1. Download
git clone <repo-url>
cd serial-port-tapper

# 2. Install dependencies
pip3 install -r requirements.txt

# 3. Make executable
chmod +x serial_tapper.py run_tap.sh

# 4. Test
./serial_tapper.py --list
```

---

## 🎯 Quick Start

### Method 1: Direct Command

```bash
# Basic monitoring
./serial_tapper.py -p /dev/ttyACM1

# Dengan log file
./serial_tapper.py -p /dev/ttyACM1 -l data_{datetime}.txt

# Multiple ports
./serial_tapper.py \
  -p /dev/ttyACM1:Dev1:9600 \
  -p /dev/ttyACM2:Dev2:115200
```

### Method 2: Background Mode 

```bash
# 1. Edit config
nano run_tap.sh

# 2. Start
./run_tap.sh start

# 3. Monitor
./run_tap.sh watch

# 4. Stop
./run_tap.sh stop
```

---

## Configuration

### Port Format

```
/dev/ttyACM1                    -> Default all
/dev/ttyACM1:Label              -> With label
/dev/ttyACM1:Label:9600         -> Custom baudrate
/dev/ttyACM1:Label:9600:RS485   -> With protocol type
```

### Parameters

| Parameter | Default | Options |
|-----------|---------|---------|
| Baudrate | 9600 | Any integer |
| Data bits | 8 | 5, 6, 7, 8 |
| Parity | N | N, E, O, M, S |
| Stop bits | 1 | 1, 1.5, 2 |
| Display | both | hex, ascii, both |
| Log format | hex | hex, ascii |
| Packet timeout | 50ms | Any integer (ms) |
| Detection | auto | auto, alternating, pattern, size, rs485, none |

### Log Filename Variables

```bash
{date}      -> 20250225
{time}      -> 143022
{datetime}  -> 20250225_143022
{timestamp} -> 1708851022

# Example:
-l session_{datetime}.txt
# Result: session_20250225_143022.txt
```

---

## Detection Modes

| Mode | Description | Best For |
|------|-------------|----------|
| **auto**  | Smart combination | Semua kasus (recommended) |
| alternating | TX-RX-TX-RX toggle | Point-to-point |
| pattern | Pattern recognition | AT commands, HTTP |
| size | Size-based | Command-response |
| rs485 | RS-485 specific | Modbus RTU |
| none | All RX | Passive monitoring |

### Auto Mode (Recommended)

```bash
./serial_tapper.py -p /dev/ttyACM1 --detection auto
```

**Cara Kerja:**
- RS-485 → Address byte detection
- RS-232/422 → Pattern + Size + Alternating
- Adaptive learning

**Handles:** RX RX TX TX, TX TX RX RX, semua pattern!

---

## Protocol Support

### RS-232 (Standard Serial)

```bash
./serial_tapper.py -p /dev/ttyACM1:Serial:115200:RS232
```

**Detection:** Pattern + Size (auto mode)

---

### RS-422 (Differential)

```bash
./serial_tapper.py -p /dev/ttyS0:Controller:38400:RS422
```

**Detection:** Same as RS-232

---

### RS-485 (Multi-drop)

```bash
./serial_tapper.py -p /dev/ttyUSB0:Modbus:19200:RS485 --detection rs485
```

**Modbus RTU:**
```bash
./serial_tapper.py \
  -p /dev/ttyUSB0:Modbus:19200:RS485 \
  --detection rs485 \
  --parity E \
  -l modbus_{date}.txt
```

**Detection:** Address byte + Function code

---

### Mixed Protocols

```bash
./serial_tapper.py \
  -p /dev/ttyACM1:Debug:115200:RS232 \
  -p /dev/ttyUSB0:Modbus:19200:RS485 \
  --detection auto
```

---

## Background Mode

### Edit run_tap.sh

```bash
nano run_tap.sh
```

**Example Configurations:**

#### Single Port
```bash
PORTS=(
    "/dev/ttyACM1:TappingPort:9600:RS232"
)
DETECTION_MODE="auto"
```

#### Multiple Ports Different Baudrates
```bash
PORTS=(
    "/dev/ttyACM0:Sensor1:9600:RS232"
    "/dev/ttyACM1:Sensor2:19200:RS232"
    "/dev/ttyS3:Gateway:115200:RS232"
)
DETECTION_MODE="auto"
PACKET_TIMEOUT=50
```

#### RS-485 Modbus
```bash
PORTS=(
    "/dev/ttyUSB0:ModbusMaster:19200:RS485"
)
PARITY="E"
DETECTION_MODE="rs485"
PACKET_TIMEOUT=30
```

#### Mixed RS-232 + RS-485
```bash
PORTS=(
    "/dev/ttyACM1:SerialDebug:115200:RS232"
    "/dev/ttyUSB0:ModbusRTU:19200:RS485"
)
DETECTION_MODE="auto"
```

### Commands

```bash
./run_tap.sh start    # Start background
./run_tap.sh stop     # Stop
./run_tap.sh status   # Status & info
./run_tap.sh watch    # Monitor data realtime
./run_tap.sh tail     # Monitor output realtime
./run_tap.sh logs     # Last 50 lines
./run_tap.sh restart  # Restart
```

---

## Examples

### Debug Serial Communication
```bash
./serial_tapper.py -p /dev/ttyUSB0:Debug:115200 -l debug_{datetime}.txt
```

### Monitor Modbus RTU
```bash
./serial_tapper.py \
  -p /dev/ttyUSB0:Modbus:19200:RS485 \
  --detection rs485 \
  --parity E \
  -l modbus_{date}.txt
```

### GPS Data Logging
```bash
./serial_tapper.py -p /dev/ttyACM0:GPS:9600 -l gps_{date}.txt
```

### Industrial PLC
```bash
./serial_tapper.py \
  -p /dev/ttyS0:PLC:38400:RS422 \
  --packet-timeout 30 \
  -l plc_{datetime}.txt
```

### High-Speed Capture
```bash
./serial_tapper.py \
  -p /dev/ttyACM1:Fast:921600 \
  --packet-timeout 5 \
  -l highspeed_{datetime}.txt
```

---

## Troubleshooting

### Permission Denied
```bash
sudo usermod -a -G dialout $USER
# Logout & login
```

### Port Busy
```bash
# Find process
lsof | grep ttyACM1

# Kill process
sudo kill -9 <PID>
```

### Data Terpotong
**Naikkan timeout:**
```bash
--packet-timeout 100  # Default: 50
```

**Panduan:**
- 2400 baud → 200ms
- 9600 baud → 50-100ms
- 115200 baud → 10-15ms
- 921600 baud → 5-10ms

### TX/RX Tidak Akurat
```bash
# Try auto mode
--detection auto

# Or specific mode
--detection pattern  # For AT commands
--detection rs485    # For Modbus
--detection none     # All RX
```

### Port Not Found
```bash
./serial_tapper.py --list
```


## Output Format

### Console
```
================================================================================
[2025-02-25 14:30:45.123] Sensor1 (/dev/ttyACM1) [RS232] → TX | Length: 14 bytes
HEX:   41 54 2B 43 47 4D 49 3D 31 0D 0A
ASCII: AT+CGMI=1..
================================================================================
```

### Log File (HEX)
```
TX : 2025-02-25 14:30:45.123 41 54 2B 43 47 4D 49 3D 31 0D 0A
RX : 2025-02-25 14:30:45.456 2B 43 47 4D 49 3A 20 51 75 65 63 74 65 6C 0D 0A
```

### Log File (ASCII)
```
TX : 2025-02-25 14:30:45.123 AT+CGMI=1[0D][0A]
RX : 2025-02-25 14:30:45.456 +CGMI: Quectel[0D][0A]
```

### Statistics
```
  Sensor1 (/dev/ttyACM1) [RS232]
    Total Packets: 245 | Total Bytes: 15680
    TX: 123 packets (5840 bytes) | RX: 122 packets (9840 bytes)
```

---

##  Command Reference

```bash
# List ports
./serial_tapper.py --list

# Basic monitoring
./serial_tapper.py -p /dev/ttyACM1

# Custom baudrate
./serial_tapper.py -p /dev/ttyACM1 -b 115200

# Multiple ports
./serial_tapper.py -p /dev/ttyACM1:Dev1:9600 -p /dev/ttyACM2:Dev2:115200

# With log
./serial_tapper.py -p /dev/ttyACM1 -l data_{datetime}.txt

# Custom detection
./serial_tapper.py -p /dev/ttyACM1 --detection pattern

# RS-485
./serial_tapper.py -p /dev/ttyUSB0:Modbus:19200:RS485 --detection rs485

# Adjust timeout
./serial_tapper.py -p /dev/ttyACM1 --packet-timeout 100

# Help
./serial_tapper.py -h
```

---

##  File Structure

```
serial-port-tapper/
├── tap.py                        # Main program
├── run_tap.sh                    # Background script
├── requirements.txt              # Dependencies
├── README.md                     # Complete guide

```

---

## Version

**v4.0 - Robust Edition** (2025-02-25)
- Smart TX/RX detection (5 modes)
- Multi-protocol (RS-232/422/485)
- Port busy protection
- Packet assembly
- Adaptive learning
- Background mode
- Full documentation

---

## License

MIT License - Free to use and modify

---

## 🤝 Contributing

Issues & PRs welcome!

---

**Made with ❤️ for serial port debugging**

**Version 4.0 - Robust Edition**