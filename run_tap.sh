#!/bin/bash
# run_tap.sh - Script untuk menjalankan Serial Port Tapper di background
# Usage: ./run_tap.sh [start|stop|status|logs|tail|watch]

#==============================================================================
# KONFIGURASI - EDIT BAGIAN INI SESUAI KEBUTUHAN ANDA
#==============================================================================

# Nama file log (bisa pakai variables: {date}, {time}, {datetime}, {timestamp})
LOG_FILENAME="tapping_{datetime}.txt"

# Port yang akan di-tap (pisahkan dengan spasi)
# Format: port:label:baudrate atau port:label atau port
PORTS=(
    "/dev/ttyACM1:TappingPort:9600"
    # "/dev/ttyS3:Gateway:115200"
    # "/dev/ttyACM2:Sensor:19200"
    # Tambahkan port lain di sini jika perlu
)

# Default baudrate (jika tidak dispesifikasikan per-port)
DEFAULT_BAUDRATE=9600

# Display mode untuk console output (hex/ascii/both)
DISPLAY_MODE="both"

# Format log file (hex/ascii)
LOG_FORMAT="hex"

# Bytesize, parity, stopbits (opsional)
BYTESIZE=8
PARITY="N"
STOPBITS=1

#==============================================================================
# JANGAN EDIT DI BAWAH INI KECUALI ANDA TAHU APA YANG ANDA LAKUKAN
#==============================================================================

# Warna
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TAPPER_SCRIPT="$SCRIPT_DIR/serial_tapper.py"
PID_FILE="$SCRIPT_DIR/tapper.pid"
OUTPUT_LOG="$SCRIPT_DIR/tapper_output.log"

# Function untuk print dengan warna
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

# Function untuk check if running
is_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            return 0
        fi
    fi
    return 1
}

# Function untuk show status
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
        
        # Get data log filename
        if [ -f "$OUTPUT_LOG" ]; then
            DATA_LOG=$(grep "Log file will be saved as:" "$OUTPUT_LOG" | tail -1 | awk '{print $NF}')
            if [ -n "$DATA_LOG" ]; then
                echo "  Data Log      : $DATA_LOG"
                if [ -f "$DATA_LOG" ]; then
                    FILE_SIZE=$(du -h "$DATA_LOG" | cut -f1)
                    LINE_COUNT=$(wc -l < "$DATA_LOG")
                    echo "  Log Size      : $FILE_SIZE ($LINE_COUNT lines)"
                fi
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
            print_warning "PID file ditemukan tapi process tidak running (cleaning up...)"
            rm -f "$PID_FILE"
        fi
    fi
    echo ""
}

# Function untuk start
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
        print_error "pyserial tidak terinstall. Install dengan: pip install pyserial"
        exit 1
    fi
    
    # Check if already running
    if is_running; then
        PID=$(cat "$PID_FILE")
        print_error "Serial Tapper sudah running dengan PID: $PID"
        echo ""
        echo "Gunakan './run_tap.sh status' untuk melihat detail"
        echo "Gunakan './run_tap.sh stop' untuk menghentikan"
        exit 1
    fi
    
    # Build command
    CMD="python3 $TAPPER_SCRIPT"
    
    for port in "${PORTS[@]}"; do
        CMD="$CMD -p $port"
    done
    
    CMD="$CMD -b $DEFAULT_BAUDRATE"
    CMD="$CMD --bytesize $BYTESIZE"
    CMD="$CMD --parity $PARITY"
    CMD="$CMD --stopbits $STOPBITS"
    CMD="$CMD -d $DISPLAY_MODE"
    CMD="$CMD -l $LOG_FILENAME"
    CMD="$CMD --log-format $LOG_FORMAT"
    
    # Show configuration
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  SERIAL PORT TAPPER - STARTING${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "Konfigurasi:"
    echo "  Ports         : ${#PORTS[@]} port(s)"
    for port in "${PORTS[@]}"; do
        echo "                  - $port"
    done
    echo "  Default Baud  : $DEFAULT_BAUDRATE"
    echo "  Display Mode  : $DISPLAY_MODE"
    echo "  Log Filename  : $LOG_FILENAME"
    echo "  Log Format    : $LOG_FORMAT"
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
    sleep 2
    if ps -p $PID > /dev/null 2>&1; then
        print_success "Serial Port Tapper berhasil dijalankan!"
        echo ""
        echo "  PID           : $PID"
        echo ""
        echo "Command untuk monitoring:"
        echo "  ./run_tap.sh status  - Lihat status & info"
        echo "  ./run_tap.sh logs    - Lihat output log"
        echo "  ./run_tap.sh tail    - Monitor output log realtime"
        echo "  ./run_tap.sh watch   - Monitor data log realtime"
        echo "  ./run_tap.sh stop    - Stop tapper"
        echo ""
    else
        print_error "Tapper gagal dijalankan atau langsung berhenti"
        echo ""
        echo "Error log:"
        cat "$OUTPUT_LOG"
        rm -f "$PID_FILE"
        exit 1
    fi
}

# Function untuk stop
stop_tapper() {
    if ! is_running; then
        print_warning "Tapper tidak sedang running"
        if [ -f "$PID_FILE" ]; then
            rm -f "$PID_FILE"
        fi
        exit 0
    fi
    
    PID=$(cat "$PID_FILE")
    print_info "Stopping Serial Port Tapper (PID: $PID)..."
    
    # Send SIGTERM
    kill -TERM $PID 2>/dev/null
    
    # Wait for process to stop (max 10 seconds)
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

# Function untuk show logs
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

# Function untuk tail logs
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

# Function untuk watch data log
watch_data_log() {
    if [ ! -f "$OUTPUT_LOG" ]; then
        print_error "Output log tidak ditemukan, tapper mungkin belum pernah dijalankan"
        exit 1
    fi
    
    # Get data log filename from output log
    DATA_LOG=$(grep "Log file will be saved as:" "$OUTPUT_LOG" | tail -1 | awk '{print $NF}')
    
    if [ -z "$DATA_LOG" ]; then
        print_error "Tidak dapat menemukan nama data log file"
        echo "Pastikan tapper sudah pernah dijalankan minimal sekali"
        exit 1
    fi
    
    if [ ! -f "$DATA_LOG" ]; then
        print_warning "Data log belum dibuat: $DATA_LOG"
        echo "Menunggu data log dibuat..."
        
        # Wait for file to be created (max 30 seconds)
        for i in {1..30}; do
            if [ -f "$DATA_LOG" ]; then
                break
            fi
            sleep 1
        done
        
        if [ ! -f "$DATA_LOG" ]; then
            print_error "Data log tidak dibuat setelah 30 detik"
            echo "Kemungkinan tidak ada komunikasi serial yang terjadi"
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

# Main script
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
        echo "  status  - Lihat status tapper"
        echo "  logs    - Lihat output log (last 50 lines)"
        echo "  tail    - Monitor output log realtime"
        echo "  watch   - Monitor data log realtime"
        echo ""
        echo "Edit konfigurasi di dalam file $0"
        echo ""
        exit 1
        ;;
esac