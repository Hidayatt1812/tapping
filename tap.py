#!/usr/bin/env python3
"""
Serial Port Tapper - Monitor komunikasi serial dengan detection pintar
Mendukung RS-232, RS-422, RS-485 dengan pattern recognition
Version: 4.0 - Robust Edition
"""

import serial
import serial.tools.list_ports
import threading
import time
import argparse
from datetime import datetime
from collections import defaultdict
import sys
import os


class SerialTapper:
    def __init__(self, tap_ports, baudrate=9600, bytesize=8, parity='N', 
                 stopbits=1, timeout=0.1, log_file=None, display_mode='both', 
                 log_format='hex', packet_timeout=0.05, detection_mode='auto'):
        """
        Initialize Serial Tapper dengan smart detection
        
        Args:
            tap_ports: List of dict - konfigurasi port
            baudrate: Default baud rate (default: 9600)
            bytesize: Data bits (default: 8)
            parity: Parity - N/E/O/M/S (default: N)
            stopbits: Stop bits (default: 1)
            timeout: Read timeout in seconds
            log_file: Path file log (optional)
            display_mode: Mode display console - hex/ascii/both
            log_format: Format data di log - hex/ascii
            packet_timeout: Timeout untuk packet assembly (default: 0.05 = 50ms)
            detection_mode: Mode deteksi TX/RX - auto/alternating/pattern/size/none
        """
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
        
        self.serial_connections = []
        self.running = False
        self.threads = []
        
        # Statistics - tracking untuk setiap port
        self.stats = defaultdict(lambda: {
            'bytes': 0, 'packets': 0, 'tx': 0, 'rx': 0, 
            'tx_bytes': 0, 'rx_bytes': 0
        })
        
        # Packet assembly - buffer untuk menggabungkan data fragmented
        self.packet_buffer = defaultdict(bytearray)
        self.last_receive_time = defaultdict(float)
        self.buffer_lock = threading.Lock()
        
        # Direction detection - untuk pattern recognition
        self.last_direction = defaultdict(lambda: "TX")  # Start dengan TX
        self.packet_history = defaultdict(list)  # History untuk learning pattern
        
        # Colors untuk output terminal
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
        
        # Assign warna untuk setiap port (cycling)
        self.color_list = ['cyan', 'green', 'yellow', 'magenta', 'blue', 'red']
    
    def list_available_ports(self):
        """List semua serial port yang tersedia di sistem"""
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
    
    def check_port_availability(self, port_name):
        """
        Check apakah port tersedia dan tidak sedang digunakan
        
        Returns:
            (bool, str) - (available, error_message)
        """
        try:
            # Coba buka port sebentar untuk test
            test = serial.Serial(
                port=port_name,
                baudrate=9600,
                timeout=0.1
            )
            test.close()
            return True, "Port available"
        except serial.SerialException as e:
            error_msg = str(e)
            if "Permission denied" in error_msg:
                return False, "Permission denied - run: sudo usermod -a -G dialout $USER"
            elif "Device or resource busy" in error_msg:
                return False, "Port sedang digunakan oleh program lain"
            elif "No such file or directory" in error_msg:
                return False, "Port tidak ditemukan di sistem"
            else:
                return False, f"Error: {error_msg}"
    
    def open_connections(self):
        """
        Buka koneksi ke semua tap ports
        Check availability dulu sebelum buka
        """
        print("\n" + "="*80)
        print("  OPENING SERIAL CONNECTIONS")
        print("="*80)
        
        for idx, tap_config in enumerate(self.tap_ports):
            port_name = tap_config['port']
            label = tap_config.get('label', port_name)
            
            # Check port availability dulu
            available, msg = self.check_port_availability(port_name)
            if not available:
                print(f"  {self.colors['red']}✗{self.colors['reset']} {label:<30} ({port_name}) - {msg}")
                print(f"\n{self.colors['red']}PROGRAM DIHENTIKAN{self.colors['reset']} - Port tidak bisa dibuka\n")
                sys.exit(1)
            
            try:
                color = self.color_list[idx % len(self.color_list)]
                
                # Get baudrate - per-port atau default
                port_baudrate = tap_config.get('baudrate', self.default_baudrate)
                
                # Buka serial port
                ser = serial.Serial(
                    port=port_name,
                    baudrate=port_baudrate,
                    bytesize=self.bytesize,
                    parity=self.parity,
                    stopbits=self.stopbits,
                    timeout=self.timeout
                )
                
                # Flush input buffer untuk clean start
                ser.reset_input_buffer()
                
                # Simpan connection info
                self.serial_connections.append({
                    'serial': ser,
                    'port': port_name,
                    'label': label,
                    'color': color,
                    'baudrate': port_baudrate,
                    'type': tap_config.get('type', 'RS232')  # RS232/RS422/RS485
                })
                
                port_type = tap_config.get('type', 'RS232')
                print(f"  {self.colors['green']}✓{self.colors['reset']} "
                      f"{label:<30} ({port_name}) @ {port_baudrate} baud [{port_type}] - CONNECTED")
                
            except serial.SerialException as e:
                print(f"  {self.colors['red']}✗{self.colors['reset']} {label:<30} ({port_name}) - ERROR: {e}")
                raise
        
        print("="*80 + "\n")
    
    def close_connections(self):
        """Tutup semua koneksi serial dengan aman"""
        print("\n" + "="*80)
        print("  CLOSING SERIAL CONNECTIONS")
        print("="*80)
        
        for conn in self.serial_connections:
            try:
                if conn['serial'].is_open:
                    conn['serial'].close()
                print(f"  {self.colors['green']}✓{self.colors['reset']} "
                      f"{conn['label']:<30} ({conn['port']}) - CLOSED")
            except Exception as e:
                print(f"  {self.colors['red']}✗{self.colors['reset']} "
                      f"{conn['label']:<30} - ERROR: {e}")
        
        print("="*80 + "\n")
    
    def format_hex(self, data):
        """Format data ke HEX dengan spasi"""
        return ' '.join(f'{b:02X}' for b in data)
    
    def format_ascii(self, data):
        """Format data ke ASCII (printable chars atau [HEX])"""
        return ''.join(chr(b) if 32 <= b < 127 else f'[{b:02X}]' for b in data)
    
    def format_mixed(self, data):
        """Format data dengan HEX dan ASCII"""
        hex_str = ' '.join(f'{b:02X}' for b in data)
        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data)
        return hex_str, ascii_str
    
    def detect_direction_smart(self, port_name, port_type, data):
        """
        SMART DETECTION - Deteksi TX/RX berdasarkan berbagai method
        
        Method yang digunakan tergantung detection_mode:
        - 'auto': Kombinasi semua method (recommended)
        - 'alternating': Simple alternating TX-RX-TX-RX
        - 'pattern': Deteksi berdasarkan pattern data (command vs response)
        - 'size': Deteksi berdasarkan size (command biasanya lebih kecil)
        - 'rs485': Khusus untuk RS-485 (detect address byte)
        - 'none': Semua jadi RX
        
        Args:
            port_name: Nama port
            port_type: Tipe port (RS232/RS422/RS485)
            data: Data packet
            
        Returns:
            str: 'TX' atau 'RX'
        """
        # Mode 'none' - semua RX
        if self.detection_mode == 'none':
            return "RX"
        
        # Mode 'alternating' - simple toggle
        if self.detection_mode == 'alternating':
            current = self.last_direction[port_name]
            new_dir = "RX" if current == "TX" else "TX"
            self.last_direction[port_name] = new_dir
            return new_dir
        
        # Mode 'pattern' - detect berdasarkan pattern
        if self.detection_mode == 'pattern':
            return self._detect_by_pattern(data)
        
        # Mode 'size' - detect berdasarkan ukuran
        if self.detection_mode == 'size':
            return self._detect_by_size(port_name, data)
        
        # Mode 'rs485' - detect berdasarkan RS-485 address
        if self.detection_mode == 'rs485' or port_type == 'RS485':
            return self._detect_rs485(data)
        
        # Mode 'auto' - kombinasi semua method (RECOMMENDED)
        if self.detection_mode == 'auto':
            # Untuk RS-485, pakai RS-485 specific detection
            if port_type == 'RS485':
                return self._detect_rs485(data)
            
            # Untuk RS-232/RS-422, kombinasi pattern + size + alternating
            pattern_result = self._detect_by_pattern(data)
            size_result = self._detect_by_size(port_name, data)
            
            # Jika pattern dan size setuju, pakai itu
            if pattern_result == size_result:
                self.last_direction[port_name] = pattern_result
                return pattern_result
            
            # Jika tidak setuju, pakai alternating sebagai fallback
            current = self.last_direction[port_name]
            new_dir = "RX" if current == "TX" else "TX"
            self.last_direction[port_name] = new_dir
            return new_dir
        
        # Default fallback: alternating
        current = self.last_direction[port_name]
        new_dir = "RX" if current == "TX" else "TX"
        self.last_direction[port_name] = new_dir
        return new_dir
    
    def _detect_by_pattern(self, data):
        """
        Deteksi TX/RX berdasarkan pattern data
        
        Pattern umum:
        - TX (Command): AT+, GET, POST, READ, WRITE, dll
        - RX (Response): OK, ERROR, +, angka, data payload
        """
        if len(data) == 0:
            return "TX"
        
        # Convert ke string untuk pattern matching (try ASCII)
        try:
            text = data.decode('ascii', errors='ignore').upper()
            
            # Pattern untuk TX (command)
            tx_patterns = ['AT+', 'AT', 'GET', 'POST', 'SET', 'READ', 'WRITE', '$', '?']
            for pattern in tx_patterns:
                if text.startswith(pattern):
                    return "TX"
            
            # Pattern untuk RX (response)
            rx_patterns = ['OK', 'ERROR', '+', 'HTTP/', '200', '404', '500']
            for pattern in rx_patterns:
                if text.startswith(pattern):
                    return "RX"
        except:
            pass
        
        # Check byte patterns (untuk binary protocols)
        # Command biasanya dimulai dengan byte rendah (< 0x80)
        # Response biasanya dimulai dengan byte tinggi atau payload
        first_byte = data[0]
        
        if first_byte < 0x20:  # Control characters - likely command
            return "TX"
        elif first_byte > 0x80:  # High byte - likely data/response
            return "RX"
        
        # Default: tidak bisa deteksi, return None (will use other methods)
        return None
    
    def _detect_by_size(self, port_name, data):
        """
        Deteksi TX/RX berdasarkan ukuran packet
        
        Logic:
        - Command (TX) biasanya lebih pendek
        - Response (RX) biasanya lebih panjang (data payload)
        - Tracking history untuk adaptive learning
        """
        # Simpan history size
        if port_name not in self.packet_history:
            self.packet_history[port_name] = []
        
        self.packet_history[port_name].append(len(data))
        
        # Keep only last 20 packets
        if len(self.packet_history[port_name]) > 20:
            self.packet_history[port_name] = self.packet_history[port_name][-20:]
        
        # Jika history masih sedikit, pakai threshold sederhana
        if len(self.packet_history[port_name]) < 4:
            # Command biasanya < 64 bytes, response bisa lebih besar
            return "TX" if len(data) < 64 else "RX"
        
        # Hitung average dari history
        avg_size = sum(self.packet_history[port_name]) / len(self.packet_history[port_name])
        
        # Jika packet ini lebih kecil dari average, likely command (TX)
        # Jika lebih besar, likely response (RX)
        return "TX" if len(data) < avg_size else "RX"
    
    def _detect_rs485(self, data):
        """
        Deteksi TX/RX untuk RS-485 berdasarkan address byte
        
        RS-485 protocol biasanya:
        - Byte pertama = address byte
        - Master TX: address target (0x01-0xF7)
        - Slave RX: address self dalam response
        
        Convention:
        - Address 0x00-0x7F: Command (TX)
        - Address 0x80-0xFF: Response (RX)
        - Atau detect dari function code byte ke-2
        """
        if len(data) < 2:
            return "TX"
        
        # Check address byte (byte pertama)
        addr_byte = data[0]
        
        # Modbus RTU convention:
        # - Slave address 1-247 (0x01-0xF7)
        # - Function code di byte ke-2
        # - Response biasanya sama dengan request + data
        
        # Jika ada function code, check bit 7
        # Bit 7 = 1 means error response (RX)
        if len(data) >= 2:
            func_code = data[1]
            if func_code & 0x80:  # Error response
                return "RX"
        
        # Simple heuristic: alternate based on last direction
        # (RS-485 is always alternating master-slave)
        current = self.last_direction.get('rs485_state', "TX")
        new_dir = "RX" if current == "TX" else "TX"
        self.last_direction['rs485_state'] = new_dir
        return new_dir
    
    def display_data(self, conn_info, data, timestamp, direction):
        """Display data ke console dengan format rapi dan color-coded"""
        label = conn_info['label']
        port = conn_info['port']
        port_type = conn_info.get('type', 'RS232')
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
        print(f"{color}[{timestamp}] {label} ({port}) [{port_type}] {arrow} {direction} | "
              f"Length: {len(data)} bytes{self.colors['reset']}")
        
        # Data display berdasarkan mode
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
                # Format data sesuai log_format
                if self.log_format == 'ascii':
                    data_str = self.format_ascii(data)
                else:
                    data_str = self.format_hex(data)
                
                # Tulis dengan format: TX/RX : timestamp data
                f.write(f"{direction} : {timestamp} {data_str}\n")
        except Exception as e:
            print(f"{self.colors['red']}Error writing to log: {e}{self.colors['reset']}")
    
    def flush_packet_buffer(self, port_name, conn_info):
        """
        Flush buffer packet yang sudah complete
        Dipanggil saat timeout atau saat ada gap timing
        """
        with self.buffer_lock:
            # Check apakah ada data di buffer
            if port_name in self.packet_buffer and len(self.packet_buffer[port_name]) > 0:
                # Ambil complete packet dari buffer
                complete_packet = bytes(self.packet_buffer[port_name])
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                
                # Detect direction dengan smart detection
                port_type = conn_info.get('type', 'RS232')
                direction = self.detect_direction_smart(port_name, port_type, complete_packet)
                
                # Display ke console
                self.display_data(conn_info, complete_packet, timestamp, direction)
                
                # Write ke log file
                if self.log_file:
                    self.write_to_log(conn_info, complete_packet, timestamp, direction)
                
                # Clear buffer setelah flush
                self.packet_buffer[port_name] = bytearray()
    
    def read_port(self, conn_info):
        """
        Thread untuk membaca data dari satu port
        Dengan packet assembly untuk menggabungkan fragments
        """
        conn = conn_info['serial']
        port = conn_info['port']
        
        while self.running:
            try:
                # Check apakah ada data di serial buffer
                if conn.in_waiting > 0:
                    # Baca semua data yang available
                    chunk = conn.read(conn.in_waiting)
                    current_time = time.time()
                    
                    with self.buffer_lock:
                        # Check apakah ini continuation atau packet baru
                        if port in self.last_receive_time:
                            time_gap = current_time - self.last_receive_time[port]
                            
                            # Jika gap > packet_timeout, ini packet baru
                            if time_gap > self.packet_timeout:
                                # Flush buffer lama dulu
                                if len(self.packet_buffer[port]) > 0:
                                    self.flush_packet_buffer(port, conn_info)
                        
                        # Tambahkan chunk ke buffer
                        self.packet_buffer[port].extend(chunk)
                        self.last_receive_time[port] = current_time
                
                # Check timeout flush (jika sudah lama tidak ada data)
                current_time = time.time()
                if port in self.last_receive_time:
                    time_since_last = current_time - self.last_receive_time[port]
                    
                    # Jika timeout dan ada data di buffer, flush
                    if time_since_last > self.packet_timeout and len(self.packet_buffer[port]) > 0:
                        self.flush_packet_buffer(port, conn_info)
                
                # Small delay untuk reduce CPU usage
                time.sleep(0.001)
                
            except serial.SerialException as e:
                print(f"{self.colors['red']}ERROR reading from {conn_info['label']}: {e}{self.colors['reset']}")
                print(f"{self.colors['red']}Port mungkin disconnect atau diambil program lain{self.colors['reset']}")
                break
            except Exception as e:
                print(f"{self.colors['red']}Unexpected error on {conn_info['label']}: {e}{self.colors['reset']}")
                break
    
    def print_statistics(self):
        """Print statistik komunikasi dengan detail TX/RX"""
        print("\n" + "="*80)
        print("  COMMUNICATION STATISTICS")
        print("="*80)
        
        for conn in self.serial_connections:
            port = conn['port']
            label = conn['label']
            port_type = conn.get('type', 'RS232')
            stats = self.stats[port]
            
            print(f"  {label:<30} ({port}) [{port_type}]")
            print(f"    Total Packets: {stats['packets']:<10} | Total Bytes: {stats['bytes']}")
            
            if self.detection_mode != 'none':
                print(f"    TX: {stats['tx']} packets ({stats['tx_bytes']} bytes) | "
                      f"RX: {stats['rx']} packets ({stats['rx_bytes']} bytes)")
        
        print("="*80 + "\n")
    
    def start_tapping(self):
        """Mulai monitoring semua port"""
        self.running = True
        
        # Print header
        print("\n" + "="*80)
        print(f"  {self.colors['bold']}SERIAL PORT TAPPER - MONITORING ACTIVE{self.colors['reset']}")
        print("="*80)
        print(f"  Default Baudrate: {self.default_baudrate} | Data: {self.bytesize} bits | "
              f"Parity: {self.parity} | Stop: {self.stopbits}")
        print(f"  Display Mode: {self.display_mode.upper()}")
        print(f"  Packet Timeout: {self.packet_timeout*1000:.0f}ms (packet assembly)")
        print(f"  Detection Mode: {self.detection_mode.upper()}")
        
        if self.log_file:
            print(f"  Log File: {self.log_file} | Format: {self.log_format.upper()}")
        
        print(f"  Monitoring {len(self.serial_connections)} port(s):")
        
        # List semua port dengan detail
        for conn in self.serial_connections:
            print(f"    - {conn['label']} ({conn['port']}) @ {conn['baudrate']} baud [{conn.get('type', 'RS232')}]")
        
        print(f"\n  {self.colors['yellow']}Press Ctrl+C to stop monitoring{self.colors['reset']}")
        print("="*80 + "\n")
        
        # Create thread untuk setiap port
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
        """Stop monitoring dan cleanup"""
        self.running = False
        
        # Flush semua remaining buffers
        for port in list(self.packet_buffer.keys()):
            for conn in self.serial_connections:
                if conn['port'] == port:
                    self.flush_packet_buffer(port, conn)
                    break
        
        # Wait untuk semua threads selesai
        for thread in self.threads:
            thread.join(timeout=1)
        
        # Print statistics
        self.print_statistics()
        
        # Close connections
        self.close_connections()
        
        if self.log_file:
            print(f"Log saved to: {self.log_file}\n")


def generate_log_filename(base_name=None, prefix="tapping", extension="txt"):
    """Generate nama file log dengan timestamp"""
    if base_name:
        if not base_name.endswith(f'.{extension}'):
            return f"{base_name}.{extension}"
        return base_name
    else:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return f"{prefix}_{timestamp}.{extension}"


def expand_log_variables(log_path):
    """
    Expand variables dalam log path
    Support: {date}, {time}, {datetime}, {timestamp}
    """
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
        description='Serial Port Tapper v4.0 - Robust Edition dengan Smart Detection',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
CONTOH PENGGUNAAN:

1. Basic monitoring:
   %(prog)s -p /dev/ttyACM1

2. Multiple ports dengan baudrate berbeda:
   %(prog)s -p /dev/ttyACM1:Dev1:9600 -p /dev/ttyACM2:Dev2:115200

3. RS-485 monitoring:
   %(prog)s -p /dev/ttyUSB0:RS485:19200:RS485 --detection rs485

4. RS-232 + RS-485 bersamaan:
   %(prog)s -p /dev/ttyACM1:Serial:9600:RS232 -p /dev/ttyUSB0:Modbus:19200:RS485

5. Custom packet timeout:
   %(prog)s -p /dev/ttyACM1 --packet-timeout 30

6. Auto detection (recommended):
   %(prog)s -p /dev/ttyACM1 --detection auto

FORMAT PORT:
  /dev/ttyACM1                    -> port saja
  /dev/ttyACM1:Label              -> port + label
  /dev/ttyACM1:Label:9600         -> port + label + baudrate
  /dev/ttyACM1:Label:9600:RS485   -> port + label + baudrate + type

DETECTION MODES:
  auto        - Smart detection (kombinasi semua method) [RECOMMENDED]
  alternating - Simple TX-RX-TX-RX toggle
  pattern     - Detect dari pattern data (AT+, OK, dll)
  size        - Detect dari ukuran packet
  rs485       - Khusus RS-485 (address byte)
  none        - Semua jadi RX (passive mode)

PORT TYPES:
  RS232       - Standard RS-232
  RS422       - RS-422 differential
  RS485       - RS-485 multi-drop

VARIABLES LOG FILE:
  {date}      -> 20250225
  {time}      -> 103045
  {datetime}  -> 20250225_103045
  {timestamp} -> 1708851045
        """
    )
    
    parser.add_argument('-p', '--port', action='append', dest='ports',
                        help='Port config: /dev/ttyACM1[:Label[:Baudrate[:Type]]]')
    
    parser.add_argument('-b', '--baudrate', type=int, default=9600,
                        help='Default baud rate (default: 9600)')
    
    parser.add_argument('--bytesize', type=int, default=8, choices=[5, 6, 7, 8],
                        help='Data bits (default: 8)')
    
    parser.add_argument('--parity', choices=['N', 'E', 'O', 'M', 'S'], default='N',
                        help='Parity (default: N)')
    
    parser.add_argument('--stopbits', type=float, choices=[1, 1.5, 2], default=1,
                        help='Stop bits (default: 1)')
    
    parser.add_argument('-d', '--display', dest='display_mode', 
                        choices=['hex', 'ascii', 'both'], default='both',
                        help='Display mode (default: both)')
    
    parser.add_argument('-l', '--log', dest='log_file',
                        help='Log file path (support variables)')
    
    parser.add_argument('--log-format', dest='log_format', 
                        choices=['hex', 'ascii'], default='hex',
                        help='Log format (default: hex)')
    
    parser.add_argument('--packet-timeout', type=int, default=50,
                        help='Packet assembly timeout in ms (default: 50)')
    
    parser.add_argument('--detection', dest='detection_mode',
                        choices=['auto', 'alternating', 'pattern', 'size', 'rs485', 'none'],
                        default='auto',
                        help='Detection mode (default: auto)')
    
    parser.add_argument('--list', action='store_true',
                        help='List available ports')
    
    args = parser.parse_args()
    
    # List ports
    if args.list:
        tapper = SerialTapper([])
        tapper.list_available_ports()
        return
    
    # Validate
    if not args.ports:
        print(f"\n{ColorText.RED}Error: Minimal 1 port harus dispesifikasikan!{ColorText.RESET}\n")
        sys.exit(1)
    
    # Parse port config
    tap_ports = []
    for port_str in args.ports:
        parts = port_str.split(':')
        
        port_config = {'port': parts[0].strip()}
        
        if len(parts) >= 2:
            port_config['label'] = parts[1].strip()
        else:
            port_config['label'] = parts[0].strip().split('/')[-1]
        
        if len(parts) >= 3:
            try:
                port_config['baudrate'] = int(parts[2].strip())
            except ValueError:
                print(f"{ColorText.RED}Invalid baudrate: {parts[2]}{ColorText.RESET}")
                sys.exit(1)
        
        if len(parts) >= 4:
            port_type = parts[3].strip().upper()
            if port_type in ['RS232', 'RS422', 'RS485']:
                port_config['type'] = port_type
            else:
                print(f"{ColorText.YELLOW}Warning: Unknown port type '{port_type}', using RS232{ColorText.RESET}")
                port_config['type'] = 'RS232'
        
        tap_ports.append(port_config)
    
    # Process log file
    log_file = None
    if args.log_file:
        log_file = expand_log_variables(args.log_file)
        if not log_file.endswith('.txt'):
            log_file = f"{log_file}.txt"
        print(f"\n{ColorText.GREEN}Log file: {log_file}{ColorText.RESET}")
    
    # Convert timeout
    packet_timeout_sec = args.packet_timeout / 1000.0
    
    # Create and start
    try:
        tapper = SerialTapper(
            tap_ports=tap_ports,
            baudrate=args.baudrate,
            bytesize=args.bytesize,
            parity=args.parity,
            stopbits=args.stopbits,
            log_file=log_file,
            display_mode=args.display_mode,
            log_format=args.log_format,
            packet_timeout=packet_timeout_sec,
            detection_mode=args.detection_mode
        )
        
        tapper.list_available_ports()
        tapper.open_connections()
        tapper.start_tapping()
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n{ColorText.RED}Error: {e}{ColorText.RESET}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)


class ColorText:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'


if __name__ == '__main__':
    main()