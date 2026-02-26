#!/bin/bash
# run_tap.sh - Jalankan Serial Port Tapper di Background
# 
# CARA KERJA:
# 1. Script ini akan jalankan serial_tapper.py di background (nohup)
# 2. PID disimpan ke file tapper.pid untuk kontrol stop/status
# 3. Output program disimpan ke tapper_output.log
# 4. Data log disimpan sesuai LOG_FILENAME yang dikonfigurasi
#
# COMMANDS:
# ./run_tap.sh start   - Jalankan tapper
# ./run_tap.sh stop    - Hentikan tapper
# ./run_tap.sh status  - Lihat status
# ./run_tap.sh logs    - Lihat output log
# ./run_tap.sh tail    - Monitor output realtime
# ./run_tap.sh watch   - Monitor data log realtime

#==============================================================================
# KONFIGURASI - EDIT SESUAI KEBUTUHAN
#==============================================================================

# ============================================================================
# NAMA FILE LOG
# ============================================================================
# Gunakan variables untuk dynamic naming:
#   {date}      -> 20250225
#   {time}      -> 103045  
#   {datetime}  -> 20250225_103045
#   {timestamp} -> 1708851045
#
# Contoh:
#   "tapping_{datetime}.txt"      -> tapping_20250225_103045.txt
#   "daily_log_{date}.txt"        -> daily_log_20250225.txt
#   "data_{timestamp}.txt"        -> data_1708851045.txt

LOG_FILENAME="tapping_{datetime}.txt"

# ============================================================================
# KONFIGURASI PORT
# ============================================================================
# Format untuk setiap port:
#   "PORT"                    -> Port saja, baudrate default
#   "PORT:LABEL"              -> Port dengan label, baudrate default  
#   "PORT:LABEL:BAUDRATE"     -> Port dengan label dan baudrate custom
#
# Contoh konfigurasi berbeda:

# --- CONTOH 1: Single Port ---
# PORTS=(
#     "/dev/ttyACM1:Device:9600"
# )

# --- CONTOH 2: Two Ports, Same Baudrate ---
# PORTS=(
#     "/dev/ttyACM1:Device1:9600"
#     "/dev/ttyACM2:Device2:9600"
# )

# --- CONTOH 3: Three Ports, Different Baudrate (RECOMMENDED) ---
# Ini contoh lengkap untuk 3 port dengan baudrate berbeda
PORTS=(
    "/dev/ttyACM1:Sensor1:9600"      # Port 1: Sensor 9600 baud
    "/dev/ttyACM2:Controller:19200"  # Port 2: Controller 19200 baud
    "/dev/ttyS3:Gateway:115200"      # Port 3: Gateway 115200 baud
)

# --- CONTOH 4: RS485 Network ---
# PORTS=(
#     "/dev/ttyUSB0:RS485_Master:19200"
#     "/dev/ttyUSB1:RS485_Slave1:19200"
#     "/dev/ttyUSB2:RS485_Slave2:19200"
# )

# --- CONTOH 5: Mixed Serial Types ---
# PORTS=(
#     "/dev/ttyACM0:RS232_Device:9600"
#     "/dev/ttyUSB0:RS422_Sensor:38400"
#     "/dev/ttyUSB1:RS485_Gateway:115200"
# )

# ============================================================================
# DEFAULT BAUDRATE
# ============================================================================
# Baudrate default jika port tidak specify baudrate sendiri
# Hanya dipakai untuk port yang formatnya: PORT atau PORT:LABEL
DEFAULT_BAUDRATE=9600

# ============================================================================
# TX/RX DETECTION MODE
# ============================================================================
# Mode deteksi arah komunikasi TX/RX:
#
#   auto        - Auto-detect (RECOMMENDED)
#                 Program akan coba berbagai metode untuk detect TX/RX
#
#   alternating - TX-RX-TX-RX pattern
#                 Cocok untuk: RS-232 point-to-point, simple request-response
#                 Contoh: Arduino serial, GPS module
#
#   pattern     - Learn dari content pattern  
#                 Cocok untuk: Protocol dengan format yang konsisten
#                 Contoh: AT commands, HTTP, custom protocol
#
#   rs485       - Khusus untuk RS485/Modbus
#                 Deteksi dari address byte dan function code
#                 Cocok untuk: Modbus RTU, RS485 multi-drop
#
#   timing      - Berdasarkan timing gap antar packet
#                 Cocok untuk: Komunikasi dengan timing yang konsisten
#
#   none        - Disable detection, semua dicatat sebagai RX
#                 Cocok untuk: Pure passive tapping
#
DETECTION_MODE="auto"

# ============================================================================
# PACKET TIMEOUT (milliseconds)
# ============================================================================
# Timeout untuk menggabungkan data fragmented menjadi 1 packet
# 
# Panduan:
#   9600 baud   : 50-100ms
#   19200 baud  : 30-50ms
#   38400 baud  : 20-40ms
#   115200 baud : 10-30ms
#   1000000+    : 5-10ms
#
# Kalau data masih terpotong-potong: NAIKKAN timeout
# Kalau ada delay antar packet: TURUNKAN timeout
#
PACKET_TIMEOUT=50

# ============================================================================
# DISPLAY MODE
# ============================================================================
# Mode tampilan data di console:
#   hex   - Tampilkan dalam format HEX
#   ascii - Tampilkan dalam format ASCII
#   both  - Tampilkan HEX dan ASCII (RECOMMENDED)
#
DISPLAY_MODE="both"

# ============================================================================
# LOG FORMAT
# ============================================================================
# Format data di log file:
#   hex   - Format HEX (RECOMMENDED)
#   ascii - Format ASCII
#
LOG_FORMAT="hex"

# ============================================================================
# SERIAL PARAMETERS (Advanced)
# ============================================================================
# Parameter serial port (jarang perlu diubah)
BYTESIZE=8        # Data bits: 5, 6, 7, 8
PARITY="N"        # Parity: N (None), E (Even), O (Odd), M (Mark), S (Space)
STOPBITS=1        # Stop bits: 1, 1.5, 2

#==============================================================================
# SCRIPT LOGIC - JANGAN EDIT DI BAWAH INI
#==============================================================================

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TAPPER_SCRIPT="$SCRIPT_DIR/serial_tapper.py"
PID_FILE="$SCRIPT_DIR/tapper.pid"
OUTPUT_LOG="$SCRIPT_DIR/tapper_output.log"

# Helper functions
print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

is_running() {
    [ -f "$PID_FILE" ] && ps -p $(cat "$PID_FILE") > /dev/null 2>&1
}

show_status() {
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  SERIAL PORT TAPPER - STATUS${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    
    if is_running; then
        PID=$(cat "$PID_FILE")
        print_success "Tapper sedang RUNNING"
        echo ""
        echo "  PID           : $PID"
        echo "  PID File      : $PID_FILE"
        echo "  Output Log    : $OUTPUT_LOG"
        echo ""
        
        # Get data log name
        if [ -f "$OUTPUT_LOG" ]; then
            DATA_LOG=$(grep "Log:" "$OUTPUT_LOG" | tail -1 | awk '{print $NF}')
            if [ -n "$DATA_LOG" ]; then
                echo "  Data Log      : $DATA_LOG"
                if [ -f "$DATA_LOG" ]; then
                    SIZE=$(du -h "$DATA_LOG" | cut -f1)
                    LINES=$(wc -l < "$DATA_LOG")
                    echo "  Log Size      : $SIZE ($LINES lines)"
                fi
            fi
        fi
        
        echo ""
        echo "  CPU & Memory  :"
        ps -p $PID -o pid,ppid,%cpu,%mem,etime,cmd | tail -1
        
        echo ""
        echo "Commands:"
        echo "  ./run_tap.sh stop    - Stop tapper"
        echo "  ./run_tap.sh logs    - Lihat output log"
        echo "  ./run_tap.sh tail    - Monitor output realtime"
        echo "  ./run_tap.sh watch   - Monitor data log realtime"
    else
        print_warning "Tapper TIDAK running"
        echo ""
        echo "Commands:"
        echo "  ./run_tap.sh start   - Start tapper"
        [ -f "$PID_FILE" ] && rm -f "$PID_FILE"
    fi
    echo ""
}

start_tapper() {
    # Check prerequisites
    if [ ! -f "$TAPPER_SCRIPT" ]; then
        print_error "serial_tapper.py tidak ditemukan"
        exit 1
    fi
    
    if ! command -v python3 &> /dev/null; then
        print_error "python3 not installed"
        exit 1
    fi
    
    if ! python3 -c "import serial" 2>/dev/null; then
        print_error "pyserial not installed"
        echo "Install: pip install pyserial"
        exit 1
    fi
    
    if is_running; then
        print_error "Tapper sudah running (PID: $(cat $PID_FILE))"
        exit 1
    fi
    
    # Build command
    CMD="python3 $TAPPER_SCRIPT"
    
    # Add ports
    for port in "${PORTS[@]}"; do
        CMD="$CMD -p $port"
    done
    
    # Add parameters
    CMD="$CMD -b $DEFAULT_BAUDRATE"
    CMD="$CMD --bytesize $BYTESIZE"
    CMD="$CMD --parity $PARITY"
    CMD="$CMD --stopbits $STOPBITS"
    CMD="$CMD -d $DISPLAY_MODE"
    CMD="$CMD -l $LOG_FILENAME"
    CMD="$CMD --log-format $LOG_FORMAT"
    CMD="$CMD --packet-timeout $PACKET_TIMEOUT"
    CMD="$CMD --detection $DETECTION_MODE"
    
    # Show config
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  STARTING SERIAL PORT TAPPER${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "Configuration:"
    echo "  Ports           : ${#PORTS[@]} port(s)"
    for port in "${PORTS[@]}"; do
        echo "                    • $port"
    done
    echo "  Default Baud    : $DEFAULT_BAUDRATE"
    echo "  Detection Mode  : $DETECTION_MODE"
    echo "  Packet Timeout  : ${PACKET_TIMEOUT}ms"
    echo "  Display Mode    : $DISPLAY_MODE"
    echo "  Log Filename    : $LOG_FILENAME"
    echo "  Log Format      : $LOG_FORMAT"
    echo ""
    echo "Files:"
    echo "  PID File        : $PID_FILE"
    echo "  Output Log      : $OUTPUT_LOG"
    echo ""
    
    # Start
    print_info "Starting tapper di background..."
    nohup $CMD > "$OUTPUT_LOG" 2>&1 &
    PID=$!
    echo $PID > "$PID_FILE"
    
    sleep 2
    if ps -p $PID > /dev/null 2>&1; then
        print_success "Tapper berhasil dijalankan!"
        echo ""
        echo "  PID: $PID"
        echo ""
        echo "Commands:"
        echo "  ./run_tap.sh status  - Status & info"
        echo "  ./run_tap.sh watch   - Monitor data realtime"
        echo "  ./run_tap.sh stop    - Stop tapper"
        echo ""
    else
        print_error "Tapper gagal start"
        echo ""
        cat "$OUTPUT_LOG"
        rm -f "$PID_FILE"
        exit 1
    fi
}

stop_tapper() {
    if ! is_running; then
        print_warning "Tapper tidak running"
        [ -f "$PID_FILE" ] && rm -f "$PID_FILE"
        return
    fi
    
    PID=$(cat "$PID_FILE")
    print_info "Stopping tapper (PID: $PID)..."
    
    kill -TERM $PID 2>/dev/null
    
    for i in {1..10}; do
        ps -p $PID > /dev/null 2>&1 || break
        sleep 1
    done
    
    if ps -p $PID > /dev/null 2>&1; then
        print_warning "Force killing..."
        kill -9 $PID 2>/dev/null
    fi
    
    rm -f "$PID_FILE"
    print_success "Tapper stopped"
}

show_logs() {
    [ ! -f "$OUTPUT_LOG" ] && print_error "Log file not found" && exit 1
    echo ""
    echo -e "${CYAN}═══ OUTPUT LOG (last 50 lines) ═══${NC}"
    echo ""
    tail -50 "$OUTPUT_LOG"
    echo ""
}

tail_logs() {
    [ ! -f "$OUTPUT_LOG" ] && print_error "Log file not found" && exit 1
    echo ""
    echo -e "${CYAN}═══ MONITORING OUTPUT LOG (Ctrl+C to exit) ═══${NC}"
    echo ""
    tail -f "$OUTPUT_LOG"
}

watch_data_log() {
    [ ! -f "$OUTPUT_LOG" ] && print_error "Tapper belum pernah run" && exit 1
    
    DATA_LOG=$(grep "Log:" "$OUTPUT_LOG" | tail -1 | awk '{print $NF}')
    
    if [ -z "$DATA_LOG" ]; then
        print_error "Data log not found"
        exit 1
    fi
    
    if [ ! -f "$DATA_LOG" ]; then
        print_warning "Data log belum dibuat: $DATA_LOG"
        echo "Waiting..."
        for i in {1..30}; do
            [ -f "$DATA_LOG" ] && break
            sleep 1
        done
        [ ! -f "$DATA_LOG" ] && print_error "Timeout" && exit 1
    fi
    
    echo ""
    echo -e "${CYAN}═══ MONITORING DATA LOG: $DATA_LOG ═══${NC}"
    echo -e "${CYAN}═══ (Ctrl+C to exit) ═══${NC}"
    echo ""
    tail -f "$DATA_LOG"
}

# Main
case "${1:-start}" in
    start) start_tapper ;;
    stop) stop_tapper ;;
    status) show_status ;;
    logs) show_logs ;;
    tail) tail_logs ;;
    watch) watch_data_log ;;
    restart) stop_tapper; sleep 2; start_tapper ;;
    *)
        echo ""
        echo "Usage: $0 {start|stop|restart|status|logs|tail|watch}"
        echo ""
        echo "Commands:"
        echo "  start   - Jalankan tapper di background"
        echo "  stop    - Hentikan tapper"
        echo "  restart - Restart tapper"
        echo "  status  - Lihat status"
        echo "  logs    - Lihat output log"
        echo "  tail    - Monitor output realtime"
        echo "  watch   - Monitor data log realtime"
        echo ""
        exit 1
        ;;
esac