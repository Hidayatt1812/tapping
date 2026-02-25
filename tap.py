#!/usr/bin/env python3
"""
Serial Port Tapper - Monitor komunikasi antar serial port
Fokus pada tapping dan deteksi arah komunikasi
Mendukung RS-232, RS-422, RS-485
"""

import serial
import serial.tools.list_ports
import threading
import time
import argparse
from datetime import datetime
from collections import defaultdict
import sys


class SerialTapper:
    def __init__(self, tap_ports, baudrate=9600, bytesize=8, parity='N', 
                 stopbits=1, timeout=0.1, log_file=None, display_mode='both'):
        """
        Initialize Serial Tapper
        
        Args:
            tap_ports: List of dict dengan format [{'port': '/dev/ttyACM1', 'label': 'Device A'}, ...]
            baudrate: Baud rate (default: 9600)
            bytesize: Data bits (default: 8)
            parity: Parity ('N', 'E', 'O', 'M', 'S')
            stopbits: Stop bits (1, 1.5, 2)
            timeout: Read timeout in seconds
            log_file: Path untuk save log (optional)
            display_mode: Mode display ('hex', 'ascii', 'both')
        """
        self.tap_ports = tap_ports
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.timeout = timeout
        self.log_file = log_file
        self.display_mode = display_mode
        
        self.serial_connections = []
        self.running = False
        self.threads = []
        
        # Statistics
        self.stats = defaultdict(lambda: {'bytes': 0, 'packets': 0})
        self.last_activity = {}
        
        # Warna untuk terminal output
        self.colors = {
            'reset': '\033[0m',
            'bold': '\033[1m',
            'red': '\033[91m',
            'green': '\033[92m',
            'yellow': '\033[93m',
            'blue': '\033[94m',
            'magenta': '\033[95m',
            'cyan': '\033[96m',
            'white': '\033[97m',
        }
        
        # Assign warna berbeda untuk setiap port
        self.color_list = ['cyan', 'green', 'yellow', 'magenta', 'blue', 'red']
    
    def list_available_ports(self):
        """List semua serial port yang tersedia"""
        ports = serial.tools.list_ports.comports()
        print("\n" + "="*80)
        print("  AVAILABLE SERIAL PORTS")
        print("="*80)
        if ports:
            for i, port in enumerate(ports, 1):
                print(f"  [{i}] {port.device:<20} - {port.description}")
        else:
            print("  No serial ports found!")
        print("="*80 + "\n")
        return [port.device for port in ports]
    
    def open_connections(self):
        """Buka koneksi ke semua tap ports"""
        print("\n" + "="*80)
        print("  OPENING SERIAL CONNECTIONS")
        print("="*80)
        
        for idx, tap_config in enumerate(self.tap_ports):
            try:
                port_name = tap_config['port']
                label = tap_config.get('label', port_name)
                color = self.color_list[idx % len(self.color_list)]
                
                ser = serial.Serial(
                    port=port_name,
                    baudrate=self.baudrate,
                    bytesize=self.bytesize,
                    parity=self.parity,
                    stopbits=self.stopbits,
                    timeout=self.timeout
                )
                
                # Flush input buffer
                ser.reset_input_buffer()
                
                self.serial_connections.append({
                    'serial': ser,
                    'port': port_name,
                    'label': label,
                    'color': color
                })
                
                print(f"  {self.colors['green']}✓{self.colors['reset']} {label:<30} ({port_name}) - CONNECTED")
                
            except serial.SerialException as e:
                print(f"  {self.colors['red']}✗{self.colors['reset']} {label:<30} ({port_name}) - ERROR: {e}")
                raise
        
        print("="*80 + "\n")
    
    def close_connections(self):
        """Tutup semua koneksi serial"""
        print("\n" + "="*80)
        print("  CLOSING SERIAL CONNECTIONS")
        print("="*80)
        
        for conn in self.serial_connections:
            try:
                if conn['serial'].is_open:
                    conn['serial'].close()
                print(f"  {self.colors['green']}✓{self.colors['reset']} {conn['label']:<30} ({conn['port']}) - CLOSED")
            except Exception as e:
                print(f"  {self.colors['red']}✗{self.colors['reset']} {conn['label']:<30} - ERROR: {e}")
        
        print("="*80 + "\n")
    
    def format_hex(self, data):
        """Format data ke HEX dengan grouping"""
        hex_str = ' '.join(f'{b:02X}' for b in data)
        return hex_str
    
    def format_ascii(self, data):
        """Format data ke ASCII (printable characters only)"""
        ascii_str = ''.join(chr(b) if 32 <= b < 127 else f'[{b:02X}]' for b in data)
        return ascii_str
    
    def format_mixed(self, data):
        """Format data dengan HEX dan ASCII side by side"""
        hex_str = ' '.join(f'{b:02X}' for b in data)
        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data)
        return hex_str, ascii_str
    
    def detect_direction(self, port_name):
        """
        Deteksi arah komunikasi berdasarkan timing dan pattern
        Mengembalikan indikasi TX/RX
        """
        current_time = time.time()
        
        if port_name in self.last_activity:
            time_diff = current_time - self.last_activity[port_name]
            # Jika ada gap waktu, kemungkinan ini adalah TX baru
            if time_diff > 0.1:  # 100ms threshold
                direction = "TX"
            else:
                direction = "RX"
        else:
            direction = "TX"
        
        self.last_activity[port_name] = current_time
        return direction
    
    def display_data(self, conn_info, data, timestamp):
        """Display data ke console dengan format yang rapi"""
        label = conn_info['label']
        port = conn_info['port']
        color = self.colors[conn_info['color']]
        direction = self.detect_direction(port)
        
        # Update statistics
        self.stats[port]['bytes'] += len(data)
        self.stats[port]['packets'] += 1
        
        # Header
        arrow = "→" if direction == "TX" else "←"
        print(f"{color}{self.colors['bold']}{'─'*80}{self.colors['reset']}")
        print(f"{color}[{timestamp}] {label} ({port}) {arrow} {direction} | Length: {len(data)} bytes{self.colors['reset']}")
        
        # Data display based on mode
        if self.display_mode == 'hex':
            hex_data = self.format_hex(data)
            print(f"{color}HEX:   {hex_data}{self.colors['reset']}")
            
        elif self.display_mode == 'ascii':
            ascii_data = self.format_ascii(data)
            print(f"{color}ASCII: {ascii_data}{self.colors['reset']}")
            
        elif self.display_mode == 'both':
            hex_data, ascii_data = self.format_mixed(data)
            print(f"{color}HEX:   {hex_data}{self.colors['reset']}")
            print(f"{color}ASCII: {ascii_data}{self.colors['reset']}")
        
        print()
    
    def write_to_log(self, conn_info, data, timestamp, direction):
        """Tulis data ke log file"""
        if not self.log_file:
            return
        
        try:
            with open(self.log_file, 'a') as f:
                hex_data = self.format_hex(data)
                ascii_data = self.format_ascii(data)
                
                f.write(f"[{timestamp}] {conn_info['label']} ({conn_info['port']}) → {direction} | {len(data)} bytes\n")
                f.write(f"  HEX:   {hex_data}\n")
                f.write(f"  ASCII: {ascii_data}\n\n")
        except Exception as e:
            print(f"{self.colors['red']}Error writing to log: {e}{self.colors['reset']}")
    
    def read_port(self, conn_info):
        """Thread untuk membaca data dari satu port"""
        conn = conn_info['serial']
        port = conn_info['port']
        
        while self.running:
            try:
                # Check if data available
                if conn.in_waiting > 0:
                    # Read all available data
                    data = conn.read(conn.in_waiting)
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    direction = self.detect_direction(port)
                    
                    # Display data
                    self.display_data(conn_info, data, timestamp)
                    
                    # Write to log if enabled
                    if self.log_file:
                        self.write_to_log(conn_info, data, timestamp, direction)
                
                # Small delay to reduce CPU usage
                time.sleep(0.001)
                
            except serial.SerialException as e:
                print(f"{self.colors['red']}ERROR reading from {conn_info['label']}: {e}{self.colors['reset']}")
                break
            except Exception as e:
                print(f"{self.colors['red']}Unexpected error on {conn_info['label']}: {e}{self.colors['reset']}")
                break
    
    def print_statistics(self):
        """Print statistik komunikasi"""
        print("\n" + "="*80)
        print("  COMMUNICATION STATISTICS")
        print("="*80)
        
        for conn in self.serial_connections:
            port = conn['port']
            label = conn['label']
            stats = self.stats[port]
            print(f"  {label:<30} ({port})")
            print(f"    Packets: {stats['packets']:<10} | Bytes: {stats['bytes']}")
        
        print("="*80 + "\n")
    
    def start_tapping(self):
        """Mulai monitoring semua port"""
        self.running = True
        
        # Header
        print("\n" + "="*80)
        print(f"  {self.colors['bold']}SERIAL PORT TAPPER - MONITORING ACTIVE{self.colors['reset']}")
        print("="*80)
        print(f"  Baudrate: {self.baudrate} | Data: {self.bytesize} bits | Parity: {self.parity} | Stop: {self.stopbits}")
        print(f"  Display Mode: {self.display_mode.upper()}")
        if self.log_file:
            print(f"  Log File: {self.log_file}")
        print(f"  Monitoring {len(self.serial_connections)} port(s)")
        print(f"\n  {self.colors['yellow']}Press Ctrl+C to stop monitoring{self.colors['reset']}")
        print("="*80 + "\n")
        
        # Create thread for each port
        for conn_info in self.serial_connections:
            thread = threading.Thread(
                target=self.read_port, 
                args=(conn_info,), 
                daemon=True,
                name=f"Tapper-{conn_info['port']}"
            )
            thread.start()
            self.threads.append(thread)
        
        # Keep main thread alive
        try:
            while self.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print(f"\n\n{self.colors['yellow']}Stopping monitoring...{self.colors['reset']}")
            self.stop_tapping()
    
    def stop_tapping(self):
        """Stop monitoring"""
        self.running = False
        
        # Wait for all threads to finish
        for thread in self.threads:
            thread.join(timeout=1)
        
        # Print statistics
        self.print_statistics()
        
        # Close connections
        self.close_connections()
        
        if self.log_file:
            print(f"Log saved to: {self.log_file}\n")


def main():
    parser = argparse.ArgumentParser(
        description='Serial Port Tapper - Monitor komunikasi serial port secara real-time',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh Penggunaan:
  # Monitor single port
  %(prog)s -p /dev/ttyACM1

  # Monitor multiple ports dengan label custom
  %(prog)s -p /dev/ttyACM1:DeviceA -p /dev/ttyACM2:DeviceB

  # Monitor dengan baudrate custom
  %(prog)s -p /dev/ttyACM1 -b 115200

  # Monitor dengan log file dan display mode
  %(prog)s -p /dev/ttyACM1 -p /dev/ttyS3 -l tapping.log -d hex

  # List available ports
  %(prog)s --list

Catatan:
  - Program ini HANYA membaca (read-only), tidak mengirim data
  - Cocok untuk tapping komunikasi RS-232, RS-422, RS-485
  - Arah komunikasi (TX/RX) dideteksi berdasarkan timing pattern
        """
    )
    
    parser.add_argument('-p', '--port', action='append', dest='ports',
                        help='Port untuk di-tap (format: /dev/ttyACM1 atau /dev/ttyACM1:Label)')
    
    parser.add_argument('-b', '--baudrate', type=int, default=9600,
                        help='Baud rate (default: 9600)')
    
    parser.add_argument('--bytesize', type=int, default=8, choices=[5, 6, 7, 8],
                        help='Data bits (default: 8)')
    
    parser.add_argument('--parity', choices=['N', 'E', 'O', 'M', 'S'], default='N',
                        help='Parity - N:None, E:Even, O:Odd, M:Mark, S:Space (default: N)')
    
    parser.add_argument('--stopbits', type=float, choices=[1, 1.5, 2], default=1,
                        help='Stop bits (default: 1)')
    
    parser.add_argument('-d', '--display', dest='display_mode', 
                        choices=['hex', 'ascii', 'both'], default='both',
                        help='Display mode (default: both)')
    
    parser.add_argument('-l', '--log', dest='log_file',
                        help='File untuk menyimpan log (optional)')
    
    parser.add_argument('--list', action='store_true',
                        help='List semua available serial ports')
    
    args = parser.parse_args()
    
    # Create temporary tapper for listing ports
    if args.list:
        tapper = SerialTapper([])
        tapper.list_available_ports()
        return
    
    # Validate input
    if not args.ports:
        print(f"\n{ColorText.RED}Error: Minimal 1 port harus dispesifikasikan!{ColorText.RESET}")
        print("Gunakan --list untuk melihat available ports")
        print("Gunakan -h untuk help\n")
        sys.exit(1)
    
    # Parse port configuration
    tap_ports = []
    for port_str in args.ports:
        if ':' in port_str:
            port, label = port_str.split(':', 1)
            tap_ports.append({'port': port.strip(), 'label': label.strip()})
        else:
            port = port_str.strip()
            tap_ports.append({'port': port, 'label': port.split('/')[-1]})
    
    # Create and start tapper
    try:
        tapper = SerialTapper(
            tap_ports=tap_ports,
            baudrate=args.baudrate,
            bytesize=args.bytesize,
            parity=args.parity,
            stopbits=args.stopbits,
            log_file=args.log_file,
            display_mode=args.display_mode
        )
        
        # List available ports first
        tapper.list_available_ports()
        
        # Open connections
        tapper.open_connections()
        
        # Start tapping
        tapper.start_tapping()
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n{ColorText.RED}Error: {e}{ColorText.RESET}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)


class ColorText:
    """Helper class for colored terminal output"""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'


if __name__ == '__main__':
    main()