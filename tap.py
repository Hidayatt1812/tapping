#!/usr/bin/env python3
"""
Serial Port Tapper - ROBUST Version
Mendukung RS-232, RS-422, RS-485 dengan deteksi pattern yang pintar

CARA KERJA:
1. Packet Assembly: Menggabungkan data fragmented berdasarkan timeout
2. Direction Detection: Berbagai metode (alternating, pattern, timing)
3. RS485 Detection: Deteksi berdasarkan address byte atau device ID
4. Error Handling: Handle port yang sudah dipakai, auto-recovery
"""

import serial
import serial.tools.list_ports
import threading
import time
import argparse
from datetime import datetime
from collections import defaultdict, deque
import sys
import os
import errno


class SerialTapper:
    """
    Main class untuk Serial Port Tapping
    
    Fitur:
    - Multi-port monitoring
    - Packet assembly untuk data fragmented  
    - TX/RX detection dengan berbagai metode
    - Support RS-232, RS-422, RS-485
    - Error handling yang robust
    """
    
    def __init__(self, tap_ports, baudrate=9600, bytesize=8, parity='N', 
                 stopbits=1, timeout=0.1, log_file=None, display_mode='both', 
                 log_format='hex', packet_timeout=0.05, detection_mode='auto'):
        """
        Inisialisasi Serial Tapper
        
        Args:
            tap_ports: List konfigurasi port [{'port': '/dev/ttyACM1', 'label': 'Dev1', 'baudrate': 9600}, ...]
            baudrate: Default baud rate (default: 9600)
            detection_mode: Mode deteksi TX/RX
                           - 'auto': Otomatis pilih metode terbaik
                           - 'alternating': TX-RX-TX-RX pattern
                           - 'pattern': Deteksi dari content pattern
                           - 'rs485': Khusus untuk RS485 (address-based)
                           - 'timing': Berdasarkan timing gap
                           - 'none': Semua dicatat sebagai RX
        """
        # Konfigurasi dasar
        self.tap_ports = tap_ports
        self.default_baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.timeout = timeout
        self.log_file = log_file
        self.display_mode = display_mode
        self.log_format = log_format
        self.packet_timeout = packet_timeout
        self.detection_mode = detection_mode
        
        # Runtime state
        self.serial_connections = []
        self.running = False
        self.threads = []
        
        # Statistics - untuk monitoring performa
        self.stats = defaultdict(lambda: {
            'bytes': 0,        # Total bytes
            'packets': 0,      # Total packets
            'tx': 0,           # TX packet count
            'rx': 0,           # RX packet count
            'tx_bytes': 0,     # TX total bytes
            'rx_bytes': 0      # RX total bytes
        })
        
        # Packet assembly - menggabungkan fragments
        self.packet_buffer = defaultdict(bytearray)  # Buffer per port
        self.last_receive_time = defaultdict(float)  # Timestamp terakhir per port
        self.buffer_lock = threading.Lock()          # Thread safety
        
        # Direction detection state
        self.last_direction = defaultdict(lambda: "TX")          # Arah terakhir per port
        self.packet_history = defaultdict(lambda: deque(maxlen=10))  # History paket
        self.consecutive_same = defaultdict(int)                 # Counter untuk consecutive same direction
        
        # Pattern learning untuk RS485
        # RS485 biasanya punya structure: [Address][Function][Data][CRC]
        # Kita learn pattern untuk identify TX vs RX
        self.tx_patterns = defaultdict(set)  # Pattern yang sering di TX
        self.rx_patterns = defaultdict(set)  # Pattern yang sering di RX
        
        # Colors untuk display
        self.colors = {
            'reset': '\033[0m',
            'bold': '\033[1m',
            'red': '\033[91m',
            'green': '\033[92m',
            'yellow': '\033[93m',
            'blue': '\033[94m',
            'magenta': '\033[95m',
            'cyan': '\033[96m',
        }
        
        self.color_list = ['cyan', 'green', 'yellow', 'magenta', 'blue', 'red']
    
    def list_available_ports(self):
        """
        List semua serial port di sistem
        Berguna untuk identifikasi port sebelum tapping
        """
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
    
    def check_port_available(self, port_name):
        """
        Check apakah port available (tidak sedang dipakai)
        
        Returns:
            tuple: (is_available, error_message)
        """
        try:
            # Coba buka port sebentar untuk test
            test_port = serial.Serial(port_name, timeout=0)
            test_port.close()
            return True, None
        except serial.SerialException as e:
            if "Permission denied" in str(e):
                return False, "Permission denied - jalankan dengan sudo atau tambahkan user ke group dialout"
            elif "Device or resource busy" in str(e) or "already open" in str(e).lower():
                return False, "Port sedang dipakai oleh aplikasi lain"
            elif "No such file or directory" in str(e):
                return False, "Port tidak ditemukan - device tidak terhubung"
            else:
                return False, str(e)
        except Exception as e:
            return False, str(e)
    
    def open_connections(self):
        """
        Buka koneksi ke semua port
        Dengan robust error handling
        """
        print("\n" + "="*80)
        print("  OPENING SERIAL CONNECTIONS")
        print("="*80)
        
        failed_ports = []
        
        for idx, tap_config in enumerate(self.tap_ports):
            port_name = tap_config['port']
            label = tap_config.get('label', port_name)
            color = self.color_list[idx % len(self.color_list)]
            port_baudrate = tap_config.get('baudrate', self.default_baudrate)
            
            # Check port availability dulu
            is_available, error_msg = self.check_port_available(port_name)
            
            if not is_available:
                print(f"  {self.colors['red']}✗{self.colors['reset']} {label:<30} ({port_name}) - ERROR")
                print(f"     → {error_msg}")
                failed_ports.append((port_name, label, error_msg))
                continue
            
            try:
                # Buka port
                ser = serial.Serial(
                    port=port_name,
                    baudrate=port_baudrate,
                    bytesize=self.bytesize,
                    parity=self.parity,
                    stopbits=self.stopbits,
                    timeout=self.timeout
                )
                
                # Flush buffer untuk clean start
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                
                # Simpan koneksi
                self.serial_connections.append({
                    'serial': ser,
                    'port': port_name,
                    'label': label,
                    'color': color,
                    'baudrate': port_baudrate
                })
                
                print(f"  {self.colors['green']}✓{self.colors['reset']} {label:<30} ({port_name}) @ {port_baudrate} baud - CONNECTED")
                
            except Exception as e:
                print(f"  {self.colors['red']}✗{self.colors['reset']} {label:<30} ({port_name}) - ERROR: {e}")
                failed_ports.append((port_name, label, str(e)))
        
        print("="*80 + "\n")
        
        # Kalau ada port yang gagal, tampilkan summary
        if failed_ports:
            print(f"{self.colors['yellow']}WARNING: {len(failed_ports)} port(s) gagal dibuka:{self.colors['reset']}")
            for port_name, label, error in failed_ports:
                print(f"  - {label} ({port_name}): {error}")
            print()
            
            # Kalau semua port gagal, stop program
            if len(self.serial_connections) == 0:
                print(f"{self.colors['red']}ERROR: Tidak ada port yang berhasil dibuka!{self.colors['reset']}")
                print("Program akan berhenti.\n")
                sys.exit(1)
            else:
                print(f"{self.colors['green']}Lanjut dengan {len(self.serial_connections)} port yang berhasil.{self.colors['reset']}\n")
                input("Tekan Enter untuk melanjutkan...")
    
    def close_connections(self):
        """Tutup semua koneksi serial dengan aman"""
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
        """Format data ke HEX string"""
        return ' '.join(f'{b:02X}' for b in data)
    
    def format_ascii(self, data):
        """Format data ke ASCII (dengan escape untuk non-printable)"""
        return ''.join(chr(b) if 32 <= b < 127 else f'[{b:02X}]' for b in data)
    
    def format_mixed(self, data):
        """Format data dengan HEX dan ASCII"""
        hex_str = ' '.join(f'{b:02X}' for b in data)
        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data)
        return hex_str, ascii_str
    
    def detect_direction_alternating(self, port_name, data):
        """
        Method 1: Alternating pattern (TX-RX-TX-RX)
        
        Cocok untuk: RS-232 point-to-point, simple request-response
        
        Logic:
        - Komunikasi biasanya alternating
        - TX diikuti RX, RX diikuti TX
        - Consecutive same direction di-limit (max 2-3 kali)
        """
        current_dir = self.last_direction[port_name]
        
        # Toggle direction
        if current_dir == "TX":
            new_dir = "RX"
        else:
            new_dir = "TX"
        
        # Update state
        self.last_direction[port_name] = new_dir
        return new_dir
    
    def detect_direction_pattern(self, port_name, data):
        """
        Method 2: Pattern recognition
        
        Cocok untuk: Protocol dengan format yang jelas
        
        Logic:
        - Learn pattern dari data
        - TX biasanya: Command, Request, Query
        - RX biasanya: Response, Acknowledgment, Data
        
        Contoh:
        - TX: AT+CMD, GET, POST, 0x01 (function code)
        - RX: OK, +RESP, HTTP 200, 0x81 (response code)
        """
        if len(data) < 2:
            return self.detect_direction_alternating(port_name, data)
        
        # Extract pattern signature (first few bytes)
        signature = tuple(data[:min(4, len(data))])
        
        # Check if signature matches known TX or RX pattern
        if signature in self.tx_patterns[port_name]:
            return "TX"
        if signature in self.rx_patterns[port_name]:
            return "RX"
        
        # Unknown pattern - use alternating logic dan learn
        direction = self.detect_direction_alternating(port_name, data)
        
        # Learn pattern
        if direction == "TX":
            self.tx_patterns[port_name].add(signature)
        else:
            self.rx_patterns[port_name].add(signature)
        
        return direction
    
    def detect_direction_rs485(self, port_name, data):
        """
        Method 3: RS485 specific
        
        Cocok untuk: RS485 multi-drop network
        
        Logic RS485:
        - Biasanya format: [Address][Function][Data][CRC]
        - Address byte pertama bisa indicate master vs slave
        - Master address biasanya 0x00 atau 0xFF
        - Slave address biasanya 0x01-0xFE
        - Function code juga bisa indicate TX vs RX
        
        Modbus RTU example:
        - TX (Master): [Slave Addr][Function][Data][CRC]
        - RX (Slave): [Slave Addr][Function][Data][CRC]
        - Function: 0x01-0x06 (read/write)
        - Response: Function + 0x80 = error
        """
        if len(data) < 2:
            return self.detect_direction_alternating(port_name, data)
        
        addr_byte = data[0]
        func_byte = data[1] if len(data) > 1 else 0
        
        # Heuristic untuk RS485/Modbus
        # Master query biasanya function 0x01-0x06, 0x0F, 0x10
        # Slave response func_byte sama, atau func_byte | 0x80 untuk error
        
        if func_byte in [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x0F, 0x10]:
            # Ini kemungkinan query (TX dari master)
            direction = "TX"
        elif func_byte >= 0x80:
            # Error response (RX dari slave)
            direction = "RX"
        else:
            # Unknown, gunakan alternating
            direction = self.detect_direction_alternating(port_name, data)
        
        # Learn pattern
        signature = (addr_byte, func_byte)
        if direction == "TX":
            self.tx_patterns[port_name].add(signature)
        else:
            self.rx_patterns[port_name].add(signature)
        
        return direction
    
    def detect_direction_timing(self, port_name, data):
        """
        Method 4: Timing-based
        
        Cocok untuk: Komunikasi dengan timing pattern yang konsisten
        
        Logic:
        - TX biasanya punya gap lebih lama sebelumnya (thinking time)
        - RX biasanya langsung setelah TX (quick response)
        - Monitor inter-packet timing
        """
        current_time = time.time()
        
        if port_name in self.last_receive_time:
            gap = current_time - self.last_receive_time[port_name]
            
            # Gap > 100ms: kemungkinan TX (new command)
            # Gap < 50ms: kemungkinan RX (quick response)
            if gap > 0.1:
                return "TX"
            else:
                return "RX"
        
        return "TX"  # Default first packet
    
    def detect_direction_auto(self, port_name, data):
        """
        Method 5: Auto - kombinasi semua metode
        
        Logic:
        1. Coba pattern recognition dulu
        2. Kalau tidak match, coba RS485 heuristic
        3. Fallback ke alternating
        """
        # Try pattern first
        signature = tuple(data[:min(4, len(data))]) if len(data) >= 2 else ()
        
        if signature in self.tx_patterns[port_name]:
            return "TX"
        if signature in self.rx_patterns[port_name]:
            return "RX"
        
        # Try RS485 heuristic
        if len(data) >= 2:
            func_byte = data[1]
            if func_byte in [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x0F, 0x10]:
                self.tx_patterns[port_name].add(signature)
                return "TX"
            elif func_byte >= 0x80:
                self.rx_patterns[port_name].add(signature)
                return "RX"
        
        # Fallback to alternating
        return self.detect_direction_alternating(port_name, data)
    
    def detect_packet_direction(self, port_name, data):
        """
        Main detection dispatcher
        Pilih metode detection sesuai mode
        """
        if self.detection_mode == 'none':
            return "RX"
        elif self.detection_mode == 'alternating':
            return self.detect_direction_alternating(port_name, data)
        elif self.detection_mode == 'pattern':
            return self.detect_direction_pattern(port_name, data)
        elif self.detection_mode == 'rs485':
            return self.detect_direction_rs485(port_name, data)
        elif self.detection_mode == 'timing':
            return self.detect_direction_timing(port_name, data)
        elif self.detection_mode == 'auto':
            return self.detect_direction_auto(port_name, data)
        else:
            # Default
            return self.detect_direction_auto(port_name, data)
    
    def display_data(self, conn_info, data, timestamp, direction):
        """Display data ke console"""
        label = conn_info['label']
        port = conn_info['port']
        color = self.colors[conn_info['color']]
        
        # Update statistics
        self.stats[port]['bytes'] += len(data)
        self.stats[port]['packets'] += 1
        if direction == "TX":
            self.stats[port]['tx'] += 1
            self.stats[port]['tx_bytes'] += len(data)
        else:
            self.stats[port]['rx'] += 1
            self.stats[port]['rx_bytes'] += len(data)
        
        # Header dengan arrow
        arrow = "→" if direction == "TX" else "←"
        print(f"{color}{self.colors['bold']}{'─'*80}{self.colors['reset']}")
        print(f"{color}[{timestamp}] {label} ({port}) {arrow} {direction} | Length: {len(data)} bytes{self.colors['reset']}")
        
        # Display data
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
        """Write data ke log file"""
        if not self.log_file:
            return
        
        try:
            with open(self.log_file, 'a') as f:
                if self.log_format == 'ascii':
                    data_str = self.format_ascii(data)
                else:
                    data_str = self.format_hex(data)
                
                f.write(f"{direction} : {timestamp} {data_str}\n")
        except Exception as e:
            print(f"{self.colors['red']}Error writing to log: {e}{self.colors['reset']}")
    
    def flush_packet_buffer(self, port_name, conn_info):
        """
        Flush buffer yang sudah complete
        Dipanggil saat timeout atau buffer penuh
        """
        with self.buffer_lock:
            if port_name in self.packet_buffer and len(self.packet_buffer[port_name]) > 0:
                # Get complete packet
                complete_packet = bytes(self.packet_buffer[port_name])
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                
                # Detect direction
                direction = self.detect_packet_direction(port_name, complete_packet)
                
                # Display and log
                self.display_data(conn_info, complete_packet, timestamp, direction)
                
                if self.log_file:
                    self.write_to_log(conn_info, complete_packet, timestamp, direction)
                
                # Clear buffer
                self.packet_buffer[port_name] = bytearray()
    
    def read_port(self, conn_info):
        """
        Thread worker untuk read port
        Dengan packet assembly dan error recovery
        """
        conn = conn_info['serial']
        port = conn_info['port']
        consecutive_errors = 0
        max_errors = 5
        
        while self.running:
            try:
                # Check data available
                if conn.in_waiting > 0:
                    # Read data
                    chunk = conn.read(conn.in_waiting)
                    current_time = time.time()
                    
                    with self.buffer_lock:
                        # Check gap untuk packet assembly
                        if port in self.last_receive_time:
                            gap = current_time - self.last_receive_time[port]
                            
                            if gap > self.packet_timeout:
                                # Gap besar, flush buffer lama
                                if len(self.packet_buffer[port]) > 0:
                                    self.flush_packet_buffer(port, conn_info)
                        
                        # Add chunk ke buffer
                        self.packet_buffer[port].extend(chunk)
                        self.last_receive_time[port] = current_time
                    
                    # Reset error counter
                    consecutive_errors = 0
                
                # Check timeout flush
                current_time = time.time()
                if port in self.last_receive_time:
                    time_since_last = current_time - self.last_receive_time[port]
                    if time_since_last > self.packet_timeout and len(self.packet_buffer[port]) > 0:
                        self.flush_packet_buffer(port, conn_info)
                
                time.sleep(0.001)  # Small delay
                
            except serial.SerialException as e:
                consecutive_errors += 1
                if consecutive_errors >= max_errors:
                    print(f"{self.colors['red']}ERROR: {conn_info['label']} - {e}{self.colors['reset']}")
                    print(f"{self.colors['yellow']}Port {port} disconnected atau error fatal{self.colors['reset']}")
                    break
                time.sleep(0.1)
            except Exception as e:
                print(f"{self.colors['red']}Unexpected error: {conn_info['label']} - {e}{self.colors['reset']}")
                break
    
    def print_statistics(self):
        """Print komunikasi statistics"""
        print("\n" + "="*80)
        print("  COMMUNICATION STATISTICS")
        print("="*80)
        
        for conn in self.serial_connections:
            port = conn['port']
            label = conn['label']
            stats = self.stats[port]
            
            print(f"\n  {label:<30} ({port})")
            print(f"    Total Packets : {stats['packets']}")
            print(f"    Total Bytes   : {stats['bytes']}")
            
            if self.detection_mode != 'none':
                print(f"    TX Packets    : {stats['tx']} ({stats['tx_bytes']} bytes)")
                print(f"    RX Packets    : {stats['rx']} ({stats['rx_bytes']} bytes)")
                
                # Ratio
                if stats['packets'] > 0:
                    tx_pct = (stats['tx'] / stats['packets']) * 100
                    rx_pct = (stats['rx'] / stats['packets']) * 100
                    print(f"    TX/RX Ratio   : {tx_pct:.1f}% / {rx_pct:.1f}%")
        
        print("\n" + "="*80 + "\n")
    
    def start_tapping(self):
        """Start monitoring"""
        self.running = True
        
        # Header
        print("\n" + "="*80)
        print(f"  {self.colors['bold']}SERIAL PORT TAPPER - MONITORING ACTIVE{self.colors['reset']}")
        print("="*80)
        print(f"  Default Baudrate  : {self.default_baudrate}")
        print(f"  Detection Mode    : {self.detection_mode.upper()}")
        print(f"  Packet Timeout    : {self.packet_timeout*1000:.0f}ms")
        print(f"  Display Mode      : {self.display_mode.upper()}")
        if self.log_file:
            print(f"  Log File          : {self.log_file}")
            print(f"  Log Format        : {self.log_format.upper()}")
        
        print(f"\n  Monitoring {len(self.serial_connections)} port(s):")
        for conn in self.serial_connections:
            print(f"    • {conn['label']:<25} ({conn['port']}) @ {conn['baudrate']} baud")
        
        print(f"\n  {self.colors['yellow']}Press Ctrl+C to stop{self.colors['reset']}")
        print("="*80 + "\n")
        
        # Start threads
        for conn_info in self.serial_connections:
            thread = threading.Thread(
                target=self.read_port,
                args=(conn_info,),
                daemon=True,
                name=f"Reader-{conn_info['port']}"
            )
            thread.start()
            self.threads.append(thread)
        
        # Main loop
        try:
            while self.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print(f"\n\n{self.colors['yellow']}Stopping...{self.colors['reset']}")
            self.stop_tapping()
    
    def stop_tapping(self):
        """Stop monitoring"""
        self.running = False
        
        # Flush remaining buffers
        for port in list(self.packet_buffer.keys()):
            for conn in self.serial_connections:
                if conn['port'] == port:
                    self.flush_packet_buffer(port, conn)
                    break
        
        # Wait threads
        for thread in self.threads:
            thread.join(timeout=1)
        
        # Show stats
        self.print_statistics()
        
        # Close connections
        self.close_connections()
        
        if self.log_file:
            print(f"Log saved: {self.log_file}\n")


def expand_log_variables(log_path):
    """Expand {date}, {time}, {datetime}, {timestamp} variables"""
    now = datetime.now()
    replacements = {
        '{date}': now.strftime('%Y%m%d'),
        '{time}': now.strftime('%H%M%S'),
        '{datetime}': now.strftime('%Y%m%d_%H%M%S'),
        '{timestamp}': str(int(now.timestamp()))
    }
    result = log_path
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, value)
    return result


def main():
    parser = argparse.ArgumentParser(
        description='Serial Port Tapper - ROBUST Version',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
DETECTION MODES:
  auto        - Auto-detect metode terbaik (recommended)
  alternating - TX-RX-TX-RX pattern (cocok untuk RS-232 point-to-point)
  pattern     - Learn dari content pattern
  rs485       - Khusus RS485/Modbus (address & function code based)
  timing      - Berdasarkan timing gap
  none        - Semua dicatat sebagai RX

CONTOH PENGGUNAAN:

1. Basic monitoring:
   %(prog)s -p /dev/ttyACM1

2. Multiple ports, beda baudrate:
   %(prog)s -p /dev/ttyACM1:Dev1:9600 -p /dev/ttyACM2:Dev2:115200

3. RS485 monitoring:
   %(prog)s -p /dev/ttyUSB0:RS485:19200 --detection rs485

4. Adjust packet timeout:
   %(prog)s -p /dev/ttyACM1 --packet-timeout 100

5. Save to log:
   %(prog)s -p /dev/ttyACM1 -l data_{datetime}.txt
        """
    )
    
    parser.add_argument('-p', '--port', action='append', dest='ports',
                        help='Format: PORT atau PORT:LABEL atau PORT:LABEL:BAUD')
    parser.add_argument('-b', '--baudrate', type=int, default=9600)
    parser.add_argument('--bytesize', type=int, default=8, choices=[5,6,7,8])
    parser.add_argument('--parity', choices=['N','E','O','M','S'], default='N')
    parser.add_argument('--stopbits', type=float, choices=[1,1.5,2], default=1)
    parser.add_argument('-d', '--display', dest='display_mode', 
                        choices=['hex','ascii','both'], default='both')
    parser.add_argument('-l', '--log', dest='log_file')
    parser.add_argument('--log-format', choices=['hex','ascii'], default='hex')
    parser.add_argument('--packet-timeout', type=int, default=50,
                        help='Timeout (ms) untuk packet assembly')
    parser.add_argument('--detection', choices=['auto','alternating','pattern','rs485','timing','none'],
                        default='auto', help='TX/RX detection mode')
    parser.add_argument('--list', action='store_true')
    
    args = parser.parse_args()
    
    if args.list:
        SerialTapper([]).list_available_ports()
        return
    
    if not args.ports:
        print("Error: Harus ada minimal 1 port!")
        print("Gunakan -h untuk help")
        sys.exit(1)
    
    # Parse ports
    tap_ports = []
    for port_str in args.ports:
        parts = port_str.split(':')
        if len(parts) == 1:
            tap_ports.append({'port': parts[0].strip(), 'label': parts[0].strip().split('/')[-1]})
        elif len(parts) == 2:
            tap_ports.append({'port': parts[0].strip(), 'label': parts[1].strip()})
        else:
            try:
                tap_ports.append({
                    'port': parts[0].strip(),
                    'label': parts[1].strip(),
                    'baudrate': int(parts[2].strip())
                })
            except:
                print(f"Error: Invalid format '{port_str}'")
                sys.exit(1)
    
    # Process log file
    log_file = None
    if args.log_file:
        log_file = expand_log_variables(args.log_file)
        if not log_file.endswith('.txt'):
            log_file += '.txt'
        print(f"Log: {log_file}\n")
    
    # Create tapper
    tapper = SerialTapper(
        tap_ports=tap_ports,
        baudrate=args.baudrate,
        bytesize=args.bytesize,
        parity=args.parity,
        stopbits=args.stopbits,
        log_file=log_file,
        display_mode=args.display_mode,
        log_format=args.log_format,
        packet_timeout=args.packet_timeout/1000.0,
        detection_mode=args.detection
    )
    
    tapper.list_available_ports()
    tapper.open_connections()
    tapper.start_tapping()


if __name__ == '__main__':
    main()