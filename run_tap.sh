#!/bin/bash
# Script untuk menjalankan Serial Port Tapper di background
# Mendukung: start, stop, status, monitor, logs

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TAPPER_SCRIPT="$SCRIPT_DIR/serial_tapper.py"
PID_FILE="$SCRIPT_DIR/tapper.pid"
LOG_DIR="$SCRIPT_DIR/logs"
SCREEN_NAME="serial_tapper"

# Warna untuk output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Fungsi untuk print dengan warna
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

# Banner
show_banner() {
    echo -e "${CYAN}"
    echo "╔═══════════════════════════════════════════════════════════╗"
    echo "║         SERIAL PORT TAPPER - Background Manager          ║"
    echo "╚═══════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# Check dependencies
check_dependencies() {
    if ! command -v python3 &> /dev/null; then
        print_error "python3 not found!"
        exit 1
    fi
    
    if ! command -v screen &> /dev/null; then
        print_error "screen not found! Installing..."
        sudo apt-get update && sudo apt-get install -y screen
    fi
}

# Create log directory
create_log_dir() {
    if [ ! -d "$LOG_DIR" ]; then
        mkdir -p "$LOG_DIR"
        print_info "Created log directory: $LOG_DIR"
    fi
}

# Check if tapper is running
is_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            return 0
        else
            rm -f "$PID_FILE"
            return 1
        fi
    fi
    return 1
}

# Start tapper
start_tapper() {
    if is_running; then
        print_warning "Tapper is already running! (PID: $(cat $PID_FILE))"
        echo "Use '$0 stop' to stop it first"
        exit 1
    fi
    
    print_info "Starting Serial Port Tapper in background..."
    
    # Parse arguments atau gunakan default
    if [ $# -eq 0 ]; then
        print_error "No port specified!"
        echo ""
        echo "Usage: $0 start [OPTIONS]"
        echo ""
        echo "Examples:"
        echo "  $0 start -p /dev/ttyACM1"
        echo "  $0 start -p /dev/ttyACM1:Dev1:9600 -p /dev/ttyACM2:Dev2:115200"
        echo "  $0 start -p /dev/ttyACM1:Tap:9600 -l tapping_{datetime}.txt"
        exit 1
    fi
    
    # Generate log filename jika tidak ada -l
    HAS_LOG_FILE=false
    for arg in "$@"; do
        if [[ "$arg" == "-l" ]] || [[ "$arg" == "--log" ]]; then
            HAS_LOG_FILE=true
            break
        fi
    done
    
    if [ "$HAS_LOG_FILE" = false ]; then
        TIMESTAMP=$(date +%Y%m%d_%H%M%S)
        AUTO_LOG="$LOG_DIR/tapping_${TIMESTAMP}.txt"
        ARGS="$@ -l $AUTO_LOG"
        print_info "Auto log file: $AUTO_LOG"
    else
        ARGS="$@"
    fi
    
    # Start in screen session
    screen -dmS "$SCREEN_NAME" bash -c "python3 $TAPPER_SCRIPT $ARGS; echo \$? > /tmp/tapper_exit_code"
    
    # Wait a bit and get PID
    sleep 1
    
    # Get screen session PID
    SCREEN_PID=$(screen -ls | grep "$SCREEN_NAME" | awk '{print $1}' | cut -d'.' -f1)
    
    if [ -n "$SCREEN_PID" ]; then
        echo "$SCREEN_PID" > "$PID_FILE"
        print_success "Tapper started successfully!"
        print_info "PID: $SCREEN_PID"
        print_info "Screen session: $SCREEN_NAME"
        echo ""
        echo "Commands:"
        echo "  $0 status    - Check status"
        echo "  $0 monitor   - Attach to running session (Ctrl+A+D to detach)"
        echo "  $0 logs      - Monitor log file in real-time"
        echo "  $0 stop      - Stop the tapper"
    else
        print_error "Failed to start tapper!"
        exit 1
    fi
}

# Stop tapper
stop_tapper() {
    if ! is_running; then
        print_warning "Tapper is not running"
        exit 1
    fi
    
    PID=$(cat "$PID_FILE")
    print_info "Stopping Serial Port Tapper (PID: $PID)..."
    
    # Send Ctrl+C to screen session
    screen -S "$SCREEN_NAME" -X stuff "^C"
    
    # Wait for graceful shutdown
    sleep 2
    
    # Force kill if still running
    if ps -p "$PID" > /dev/null 2>&1; then
        print_warning "Graceful shutdown failed, force killing..."
        kill -9 "$PID" 2>/dev/null
        screen -S "$SCREEN_NAME" -X quit 2>/dev/null
    fi
    
    rm -f "$PID_FILE"
    print_success "Tapper stopped"
}

# Restart tapper
restart_tapper() {
    print_info "Restarting Serial Port Tapper..."
    
    if is_running; then
        stop_tapper
        sleep 2
    fi
    
    # Restart dengan argumen yang sama (jika ada di history)
    if [ -f "$SCRIPT_DIR/.last_command" ]; then
        LAST_CMD=$(cat "$SCRIPT_DIR/.last_command")
        print_info "Using last command: $LAST_CMD"
        eval "$0 start $LAST_CMD"
    else
        print_error "No previous command found"
        echo "Please use: $0 start [OPTIONS]"
    fi
}

# Show status
show_status() {
    echo ""
    if is_running; then
        PID=$(cat "$PID_FILE")
        print_success "Tapper is RUNNING"
        echo ""
        echo "  PID:            $PID"
        echo "  Screen session: $SCREEN_NAME"
        echo "  Uptime:         $(ps -p $PID -o etime= | xargs)"
        echo "  Memory:         $(ps -p $PID -o rss= | awk '{printf "%.2f MB", $1/1024}')"
        
        # Find latest log file
        LATEST_LOG=$(find "$LOG_DIR" -name "*.txt" -type f -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)
        if [ -n "$LATEST_LOG" ]; then
            echo "  Latest log:     $LATEST_LOG"
            LOG_SIZE=$(du -h "$LATEST_LOG" 2>/dev/null | cut -f1)
            LOG_LINES=$(wc -l < "$LATEST_LOG" 2>/dev/null)
            echo "  Log size:       $LOG_SIZE ($LOG_LINES lines)"
        fi
        echo ""
    else
        print_warning "Tapper is NOT running"
        echo ""
    fi
}

# Monitor live session
monitor_session() {
    if ! is_running; then
        print_error "Tapper is not running!"
        exit 1
    fi
    
    print_info "Attaching to tapper session..."
    print_warning "Press Ctrl+A then D to detach (keep running in background)"
    echo ""
    sleep 2
    
    screen -r "$SCREEN_NAME"
}

# Monitor log file
monitor_logs() {
    # Find latest log file
    LATEST_LOG=$(find "$LOG_DIR" -name "*.txt" -type f -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)
    
    if [ -z "$LATEST_LOG" ]; then
        print_error "No log file found in $LOG_DIR"
        exit 1
    fi
    
    print_info "Monitoring log file: $LATEST_LOG"
    print_warning "Press Ctrl+C to stop monitoring"
    echo ""
    sleep 1
    
    tail -f "$LATEST_LOG"
}

# List log files
list_logs() {
    echo ""
    print_info "Available log files:"
    echo ""
    
    if [ ! -d "$LOG_DIR" ]; then
        print_warning "No logs directory found"
        exit 0
    fi
    
    LOGS=$(find "$LOG_DIR" -name "*.txt" -type f -printf '%T@ %p\n' 2>/dev/null | sort -rn)
    
    if [ -z "$LOGS" ]; then
        print_warning "No log files found"
        exit 0
    fi
    
    echo "$LOGS" | while read -r line; do
        LOG_FILE=$(echo "$line" | cut -d' ' -f2-)
        LOG_NAME=$(basename "$LOG_FILE")
        LOG_SIZE=$(du -h "$LOG_FILE" 2>/dev/null | cut -f1)
        LOG_DATE=$(stat -c %y "$LOG_FILE" 2>/dev/null | cut -d'.' -f1)
        LOG_LINES=$(wc -l < "$LOG_FILE" 2>/dev/null)
        
        echo "  📄 $LOG_NAME"
        echo "     Size: $LOG_SIZE | Lines: $LOG_LINES | Date: $LOG_DATE"
        echo ""
    done
}

# View specific log
view_log() {
    if [ -z "$1" ]; then
        print_error "Please specify log file"
        echo "Usage: $0 view <log_file>"
        echo ""
        list_logs
        exit 1
    fi
    
    LOG_FILE="$LOG_DIR/$1"
    
    if [ ! -f "$LOG_FILE" ]; then
        print_error "Log file not found: $LOG_FILE"
        exit 1
    fi
    
    print_info "Viewing log file: $LOG_FILE"
    echo ""
    
    less "$LOG_FILE"
}

# Clean old logs
clean_logs() {
    if [ ! -d "$LOG_DIR" ]; then
        print_warning "No logs directory found"
        exit 0
    fi
    
    print_warning "This will delete ALL log files in $LOG_DIR"
    read -p "Are you sure? (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -f "$LOG_DIR"/*.txt
        print_success "All logs deleted"
    else
        print_info "Cancelled"
    fi
}

# Main script
main() {
    check_dependencies
    create_log_dir
    
    case "${1:-}" in
        start)
            shift
            # Save command untuk restart
            echo "$@" > "$SCRIPT_DIR/.last_command"
            start_tapper "$@"
            ;;
        stop)
            stop_tapper
            ;;
        restart)
            restart_tapper
            ;;
        status)
            show_status
            ;;
        monitor)
            monitor_session
            ;;
        logs)
            monitor_logs
            ;;
        list)
            list_logs
            ;;
        view)
            shift
            view_log "$@"
            ;;
        clean)
            clean_logs
            ;;
        *)
            show_banner
            echo "Usage: $0 {start|stop|restart|status|monitor|logs|list|view|clean}"
            echo ""
            echo "Commands:"
            echo "  start [OPTIONS]  - Start tapper in background"
            echo "  stop             - Stop the tapper"
            echo "  restart          - Restart with last command"
            echo "  status           - Show tapper status"
            echo "  monitor          - Attach to running session (Ctrl+A+D to detach)"
            echo "  logs             - Monitor latest log file (Ctrl+C to stop)"
            echo "  list             - List all log files"
            echo "  view <file>      - View specific log file"
            echo "  clean            - Delete all log files"
            echo ""
            echo "Examples:"
            echo "  $0 start -p /dev/ttyACM1:Tap:9600"
            echo "  $0 start -p /dev/ttyACM1:Dev1:9600 -p /dev/ttyS3:Dev2:115200"
            echo "  $0 start -p /dev/ttyACM1 -b 115200 -l custom_log.txt"
            echo "  $0 status"
            echo "  $0 monitor    # Attach to see real-time output"
            echo "  $0 logs       # Follow log file"
            echo ""
            exit 1
            ;;
    esac
}

# Run main
main "$@"