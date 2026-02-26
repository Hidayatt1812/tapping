#!/bin/bash
################################################################################
# run_tap.sh - Script untuk menjalankan Serial Port Tapper di background
# 
# Fitur:
# - Jalankan tapper sebagai background process
# - Monitoring realtime (watch/tail)
# - Start/stop/restart/status
# - Konfigurasi mudah untuk pemula
#
# Cara pakai:
#   ./run_tap.sh start   - Jalankan di background
#   ./run_tap.sh stop    - Hentikan
#   ./run_tap.sh status  - Lihat status
#   ./run_tap.sh watch   - Monitor data log realtime
#   ./run_tap.sh tail    - Monitor output log realtime
#
################################################################################

#==============================================================================
# KONFIGURASI - EDIT BAGIAN INI SESUAI KEBUTUHAN
#==============================================================================

# -------------------------
# NAMA FILE LOG
# -------------------------
# Nama file untuk menyimpan data komunikasi serial
# Bisa pakai variables: {date}, {time}, {datetime}, {timestamp}
#
# Contoh:
#   "tapping.txt"                    -> Nama fixed
#   "tapping_{datetime}.txt"         -> tapping_20250225_103045.txt
#   "daily_log_{date}.txt"           -> daily_log_20250225.txt
#   "session_{timestamp}.txt"        -> session_1708851045.txt
#
LOG_FILENAME="tapping_{datetime}.txt"


# -------------------------
# KONFIGURASI PORT
# -------------------------
# Array berisi port yang akan di-tap
# Format: "/dev/portname:Label:Baudrate:Type"
#
# Penjelasan format:
#   /dev/ttyACM1                    -> Port saja (label=ttyACM1, baud=default, type=RS232)
#   /dev/ttyACM1:MyDevice           -> Port + label (baud=default, type=RS232)
#   /dev/ttyACM1:MyDevice:9600      -> Port + label + baudrate (type=RS232)
#   /dev/ttyACM1:MyDevice:9600:RS485 -> Port + label + baudrate + type
#
# Port Types yang didukung:
#   RS232  - Standard RS-232 (default)
#   RS422  - RS-422 differential signaling
#   RS485  - RS-485 multi-drop network
#

# ===== CONTOH 1: Single Port RS-232 =====
# Tap satu port RS-232 dengan baudrate 9600
# PORTS=(
#     "/dev/ttyACM1:TappingPort:9600:RS232"
# )

# ===== CONTOH 2: Multiple Ports dengan Baudrate Berbeda =====
# Tap 3 port dengan baudrate berbeda-beda
# PORTS=(
#     "/dev/ttyACM1:Sensor1:9600:RS232"
#     "/dev/ttyACM2:Sensor2:19200:RS232"
#     "/dev/ttyS3:Gateway:115200:RS232"
# )

# ===== CONTOH 3: RS-485 Modbus Monitoring =====
# Monitoring komunikasi RS-485 (Modbus RTU)
# PORTS=(
#     "/dev/ttyUSB0:ModbusMaster:19200:RS485"
# )

# ===== CONTOH 4: RS-232 + RS-485 Bersamaan =====
# Monitor RS-232 dan RS-485 dalam waktu bersamaan
# PORTS=(
#     "/dev/ttyACM1:SerialDebug:115200:RS232"
#     "/dev/ttyUSB0:ModbusRTU:19200:RS485"
# )

# ===== CONTOH 5: RS-422 Industrial =====
# Monitor RS-422 untuk industrial automation
# PORTS=(
#     "/dev/ttyS0:Controller:38400:RS422"
#     "/dev/ttyS1:Sensors:38400:RS422"
# )

# ===== KONFIGURASI AKTIF =====
# Uncomment (hapus #) salah satu contoh di atas, atau buat sendiri
# Default: Single port RS-232
PORTS=(
    "/dev/ttyACM1:TappingPort:9600:RS485"
)


# -------------------------
# PARAMETER SERIAL
# -------------------------
# Default baudrate (jika tidak dispesifikasikan per-port)
DEFAULT_BAUDRATE=9600

# Data bits: 5, 6, 7, atau 8
BYTESIZE=8

# Parity: N (None), E (Even), O (Odd), M (Mark), S (Space)
PARITY="N"

# Stop bits: 1, 1.5, atau 2
STOPBITS=1


# -------------------------
# DISPLAY & LOG FORMAT
# -------------------------
# Display mode untuk output console
# Pilihan: "hex", "ascii", "both"
#   hex   - Tampilkan dalam format hexadecimal (48 65 6C 6C 6F)
#   ascii - Tampilkan dalam format ASCII (Hello atau [48][65][6C])
#   both  - Tampilkan HEX dan ASCII
DISPLAY_MODE="both"

# Format data di log file
# Pilihan: "hex", "ascii"
LOG_FORMAT="hex"


# -------------------------
# PACKET ASSEMBLY
# -------------------------
# Packet timeout (dalam milliseconds)
# Waktu tunggu untuk menggabungkan data yang terpotong (fragmented)
#
# Panduan:
#   9600 baud    -> 50-100ms
#   19200 baud   -> 30-50ms
#   115200 baud  -> 10-30ms
#   1000000 baud -> 5-10ms
#
# Jika data masih terpotong-potong: NAIKKAN nilai ini
# Jika ada delay antar packet: KURANGI nilai ini
PACKET_TIMEOUT=50


# -------------------------
# TX/RX DETECTION MODE
# -------------------------
# Mode deteksi arah komunikasi (TX atau RX)
# Pilihan: "auto", "alternating", "pattern", "size", "rs485", "none"
#
#   auto        - Smart detection (recommended) - kombinasi semua method
#   alternating - Simple toggle TX-RX-TX-RX
#   pattern     - Deteksi dari pattern data (AT+, OK, GET, dll)
#   size        - Deteksi dari ukuran packet (command pendek, response panjang)
#   rs485       - Khusus untuk RS-485 (deteksi dari address byte)
#   none        - Semua dicatat sebagai RX (passive mode)
#
# Untuk RS-485: gunakan "rs485" atau "auto"
# Untuk RS-232/RS-422: gunakan "auto" atau "pattern"
DETECTION_MODE="auto"


#==============================================================================
# ADVANCED CONFIGURATION (Jarang perlu diubah)
#==============================================================================

# Lokasi script tapper
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TAPPER_SCRIPT="$SCRIPT_DIR/serial_tapper.py"

# File untuk menyimpan PID (Process ID)
PID_FILE="$SCRIPT_DIR/tapper.pid"

# File untuk menyimpan output program (untuk debugging)
OUTPUT_LOG="$SCRIPT_DIR/tapper_output.log"


#==============================================================================
# INTERNAL FUNCTIONS - JANGAN EDIT DI BAWAH INI
#==============================================================================

# Warna untuk output terminal
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# Print functions dengan warna
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if tapper is running
is_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            return 0  # Running
        fi
    fi
    return 1  # Not running
}

# Show status
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
        
        # Get data log filename dari output
        if [ -f "$OUTPUT_LOG" ]; then
            DATA_LOG=$(grep "Log file:" "$OUTPUT_LOG" | tail -1 | awk '{print $NF}')
            if [ -n "$DATA_LOG" ] && [ -f "$DATA_LOG" ]; then
                FILE_SIZE=$(du -h "$DATA_LOG" | cut -f1)
                LINE_COUNT=$(wc -l < "$DATA_LOG")
                echo "  Data Log      : $DATA_LOG"
                echo "  Log Size      : $FILE_SIZE ($LINE_COUNT lines)"
            fi
        fi
        
        echo ""
        echo "  CPU & Memory  :"
        ps -p $PID -o pid,ppid,%cpu,%mem,etime,cmd | tail -1
        
        echo ""
        echo "Command:"
        echo "  ./run_tap.sh stop    - Stop tapper"
        echo "  ./run_tap.sh logs    - Lihat output log"
        echo "  ./run_tap.sh tail    - Monitor output log realtime"
        echo "  ./run_tap.sh watch   - Monitor data log realtime"
    else
        print_warning "Tapper TIDAK sedang running"
        echo ""
        echo "Command:"
        echo "  ./run_tap.sh start   - Start tapper"
        
        if [ -f "$PID_FILE" ]; then
            print_warning "Cleaning up stale PID file..."
            rm -f "$PID_FILE"
        fi
    fi
    echo ""
}

# Start tapper
start_tapper() {
    # Check prerequisites
    if [ ! -f "$TAPPER_SCRIPT" ]; then
        print_error "serial_tapper.py tidak ditemukan di $SCRIPT_DIR"
        exit 1
    fi
    
    if ! command -v python3 &> /dev/null; then
        print_error "python3 tidak terinstall"
        exit 1
    fi
    
    if ! python3 -c "import serial" &> /dev/null 2>&1; then
        print_error "pyserial tidak terinstall"
        echo "Install dengan: pip3 install pyserial"
        exit 1
    fi
    
    # Check if already running
    if is_running; then
        PID=$(cat "$PID_FILE")
        print_error "Serial Tapper sudah running dengan PID: $PID"
        echo ""
        echo "Gunakan './run_tap.sh status' untuk detail"
        echo "Gunakan './run_tap.sh stop' untuk stop"
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
    
    # Show configuration
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  SERIAL PORT TAPPER - STARTING${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "Konfigurasi:"
    echo "  Ports         : ${#PORTS[@]} port(s)"
    for i in "${!PORTS[@]}"; do
        port_info="${PORTS[$i]}"
        # Parse untuk display yang lebih baik
        IFS=':' read -ra PARTS <<< "$port_info"
        port_dev="${PARTS[0]}"
        port_label="${PARTS[1]:-${port_dev##*/}}"
        port_baud="${PARTS[2]:-$DEFAULT_BAUDRATE}"
        port_type="${PARTS[3]:-RS232}"
        echo "                  [$((i+1))] $port_dev"
        echo "                      Label: $port_label"
        echo "                      Baud:  $port_baud"
        echo "                      Type:  $port_type"
    done
    echo ""
    echo "  Default Baud  : $DEFAULT_BAUDRATE"
    echo "  Data Bits     : $BYTESIZE"
    echo "  Parity        : $PARITY"
    echo "  Stop Bits     : $STOPBITS"
    echo "  Display Mode  : $DISPLAY_MODE"
    echo "  Log Filename  : $LOG_FILENAME"
    echo "  Log Format    : $LOG_FORMAT"
    echo "  Packet Timeout: ${PACKET_TIMEOUT}ms"
    echo "  Detection Mode: $DETECTION_MODE"
    echo ""
    echo "Files:"
    echo "  PID File      : $PID_FILE"
    echo "  Output Log    : $OUTPUT_LOG"
    echo ""
    
    # Run in background
    print_info "Starting Serial Port Tapper di background..."
    nohup $CMD > "$OUTPUT_LOG" 2>&1 &
    PID=$!
    
    # Save PID
    echo $PID > "$PID_FILE"
    
    # Wait and check
    sleep 3
    if ps -p $PID > /dev/null 2>&1; then
        print_success "Serial Port Tapper berhasil dijalankan!"
        echo ""
        echo "  PID           : $PID"
        echo ""
        
        # Check for errors in output
        if grep -q "ERROR\|Error\|DIHENTIKAN" "$OUTPUT_LOG"; then
            print_error "Ada error saat start. Lihat output log:"
            echo ""
            tail -20 "$OUTPUT_LOG"
            echo ""
            stop_tapper
            exit 1
        fi
        
        echo "Command untuk monitoring:"
        echo "  ./run_tap.sh status  - Lihat status & info"
        echo "  ./run_tap.sh logs    - Lihat output log"
        echo "  ./run_tap.sh tail    - Monitor output log realtime"
        echo "  ./run_tap.sh watch   - Monitor data log realtime"
        echo "  ./run_tap.sh stop    - Stop tapper"
        echo ""
    else
        print_error "Tapper gagal start atau langsung berhenti"
        echo ""
        echo "Error log:"
        cat "$OUTPUT_LOG"
        rm -f "$PID_FILE"
        exit 1
    fi
}

# Stop tapper
stop_tapper() {
    if ! is_running; then
        print_warning "Tapper tidak sedang running"
        if [ -f "$PID_FILE" ]; then
            rm -f "$PID_FILE"
        fi
        return 0
    fi
    
    PID=$(cat "$PID_FILE")
    print_info "Stopping Serial Port Tapper (PID: $PID)..."
    
    # Send SIGTERM (graceful shutdown)
    kill -TERM $PID 2>/dev/null
    
    # Wait up to 10 seconds
    for i in {1..10}; do
        if ! ps -p $PID > /dev/null 2>&1; then
            break
        fi
        sleep 1
    done
    
    # Force kill if still running
    if ps -p $PID > /dev/null 2>&1; then
        print_warning "Process tidak berhenti, force killing..."
        kill -9 $PID 2>/dev/null
        sleep 1
    fi
    
    # Cleanup
    rm -f "$PID_FILE"
    
    if ! ps -p $PID > /dev/null 2>&1; then
        print_success "Tapper berhasil dihentikan"
    else
        print_error "Gagal menghentikan tapper"
        exit 1
    fi
}

# Show output log
show_logs() {
    if [ ! -f "$OUTPUT_LOG" ]; then
        print_error "Output log tidak ditemukan: $OUTPUT_LOG"
        exit 1
    fi
    
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  OUTPUT LOG (last 50 lines)${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    tail -50 "$OUTPUT_LOG"
    echo ""
}

# Tail output log (realtime)
tail_logs() {
    if [ ! -f "$OUTPUT_LOG" ]; then
        print_error "Output log tidak ditemukan: $OUTPUT_LOG"
        exit 1
    fi
    
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  MONITORING OUTPUT LOG (Ctrl+C untuk keluar)${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    tail -f "$OUTPUT_LOG"
}

# Watch data log (realtime)
watch_data_log() {
    if [ ! -f "$OUTPUT_LOG" ]; then
        print_error "Output log tidak ditemukan"
        exit 1
    fi
    
    # Get data log filename
    DATA_LOG=$(grep "Log file:" "$OUTPUT_LOG" | tail -1 | awk '{print $NF}')
    
    if [ -z "$DATA_LOG" ]; then
        print_error "Tidak dapat menemukan nama data log file"
        echo "Pastikan tapper sudah pernah dijalankan"
        exit 1
    fi
    
    if [ ! -f "$DATA_LOG" ]; then
        print_warning "Data log belum dibuat: $DATA_LOG"
        echo "Menunggu data log dibuat (max 30s)..."
        
        for i in {1..30}; do
            if [ -f "$DATA_LOG" ]; then
                break
            fi
            sleep 1
        done
        
        if [ ! -f "$DATA_LOG" ]; then
            print_error "Data log tidak dibuat setelah 30 detik"
            echo "Kemungkinan tidak ada komunikasi serial"
            exit 1
        fi
    fi
    
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  MONITORING DATA LOG: $DATA_LOG${NC}"
    echo -e "${CYAN}  (Ctrl+C untuk keluar)${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    tail -f "$DATA_LOG"
}

# Main script execution
case "${1:-start}" in
    start)
        start_tapper
        ;;
    stop)
        stop_tapper
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    tail)
        tail_logs
        ;;
    watch)
        watch_data_log
        ;;
    restart)
        echo ""
        print_info "Restarting Serial Port Tapper..."
        stop_tapper
        sleep 2
        start_tapper
        ;;
    *)
        echo ""
        echo "Usage: $0 {start|stop|restart|status|logs|tail|watch}"
        echo ""
        echo "Commands:"
        echo "  start   - Jalankan tapper di background"
        echo "  stop    - Hentikan tapper"
        echo "  restart - Restart tapper"
        echo "  status  - Lihat status tapper (PID, CPU, memory)"
        echo "  logs    - Lihat output log (last 50 lines)"
        echo "  tail    - Monitor output log realtime (Ctrl+C keluar)"
        echo "  watch   - Monitor data log realtime (Ctrl+C keluar)"
        echo ""
        echo "Konfigurasi:"
        echo "  Edit bagian KONFIGURASI di file ini ($0)"
        echo "  untuk mengubah port, baudrate, detection mode, dll."
        echo ""
        exit 1
        ;;
esac