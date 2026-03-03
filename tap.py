#!/usr/bin/env python3
"""
Serial Port Tapper v5.0 - Ultimate Edition
Full per-port configuration dengan hardware-aware detection
Mendukung RS-232, RS-422, RS-485 dengan setting individual

Based on MAX485 hardware schematic analysis
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
import json


class SerialTapper:
    def __init__(self, tap_ports, log_file=None, display_mode='both', log_format='hex'):
        """
        Initialize Serial Tapper dengan per-port configuration
        
        Args:
            tap_ports: List of dict dengan full configuration per-port
                      {
                          'port': '/dev/ttyACM1',
                          'label': 'Device1',
                          'baudrate': 9600,
                          'bytesize': 8,
                          'parity': 'N',
                          'stopbits': 1,
                          'type': 'RS232',  # RS232/RS422/RS485
                          'detection': 'auto',  # auto/alternating/pattern/size/rs485/none
                          'packet_timeout': 0.05  # in seconds
                      }
            log_file: Path file log (optional)
            display_mode: Mode display console - hex/ascii/both
            log_format: Format data di log - hex/ascii
        """
        self.tap_ports = tap_ports
        self.log_file = log_file
        self.display_mode = display_mode
        self.log_format = log_format
        
        self.serial_connections = []
        self.running = False
        self.threads = []
        
        # Statistics per port
        self.stats = defaultdict(lambda: {
            'bytes': 0, 'packets': 0, 'tx': 0, 'rx': 0, 
            'tx_bytes': 0, 'rx_bytes': 0
        })
        
        # Packet assembly per port
        self.packet_buffer = defaultdict(bytearray)
        self.last_receive_time = defaultdict(float)
        self.buffer_lock = threading.Lock()
        
        # Direction detection per port
        self.last_direction = defaultdict(lambda: "TX")
        self.packet_history = defaultdict(list)
        self.last_packet_time = defaultdict(float)
        
        # Colors
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
    
    def check_port_availability(self, port_name):
        """Check apakah port available"""
        try:
            test = serial.Serial(port=port_name, baudrate=9600, timeout=0.1)
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
        """Buka koneksi ke semua tap ports dengan individual configuration"""
        print("\n" + "="*80)
        print("  OPENING SERIAL CONNECTIONS")
        print("="*80)
        
        for idx, config in enumerate(self.tap_ports):
            port_name = config['port']
            label = config.get('label', port_name.split('/')[-1])
            
            # Check availability
            available, msg = self.check_port_availability(port_name)
            if not available:
                print(f"  {self.colors['red']}✗{self.colors['reset']} {label:<30} ({port_name}) - {msg}")
                print(f"\n{self.colors['red']}PROGRAM DIHENTIKAN{self.colors['reset']} - Port tidak bisa dibuka\n")
                sys.exit(1)
            
            try:
                color = self.color_list[idx % len(self.color_list)]
                
                # Get per-port configuration
                baudrate = config.get('baudrate', 9600)
                bytesize = config.get('bytesize', 8)
                parity = config.get('parity', 'N')
                stopbits = config.get('stopbits', 1)
                timeout = config.get('timeout', 0.1)
                port_type = config.get('type', 'RS232')
                detection = config.get('detection', 'auto')
                packet_timeout = config.get('packet_timeout', 0.05)
                
                # Open serial port
                ser = serial.Serial(
                    port=port_name,
                    baudrate=baudrate,
                    bytesize=bytesize,
                    parity=parity,
                    stopbits=stopbits,
                    timeout=timeout
                )
                
                ser.reset_input_buffer()
                
                # Store connection info dengan full config
                self.serial_connections.append({
                    'serial': ser,
                    'port': port_name,
                    'label': label,
                    'color': color,
                    'baudrate': baudrate,
                    'bytesize': bytesize,
                    'parity': parity,
                    'stopbits': stopbits,
                    'type': port_type,
                    'detection': detection,
                    'packet_timeout': packet_timeout
                })
                
                print(f"  {self.colors['green']}✓{self.colors['reset']} "
                      f"{label:<30} ({port_name})")
                print(f"      Baud: {baudrate} | Data: {bytesize}{parity}{stopbits} | "
                      f"Type: {port_type} | Detection: {detection} | "
                      f"Timeout: {packet_timeout*1000:.0f}ms")
                
            except serial.SerialException as e:
                print(f"  {self.colors['red']}✗{self.colors['reset']} {label:<30} - ERROR: {e}")
                raise
        
        print("="*80 + "\n")
    
    def close_connections(self):
        """Tutup semua koneksi"""
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
        """Format data ke HEX"""
        return ' '.join(f'{b:02X}' for b in data)
    
    def format_ascii(self, data):
        """Format data ke ASCII"""
        return ''.join(chr(b) if 32 <= b < 127 else f'[{b:02X}]' for b in data)
    
    def format_mixed(self, data):
        """Format HEX dan ASCII"""
        hex_str = ' '.join(f'{b:02X}' for b in data)
        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data)
        return hex_str, ascii_str
    
    def _analyze_rs485_packet_structure(self, data):
        """
        Analisis struktur packet Modbus RTU untuk RS-485
        Berdasarkan MAX485 hardware behavior
        
        Returns:
            'TX', 'RX', or None
        """
        if len(data) < 4:
            return None
        
        addr = data[0]
        func = data[1]
        
        # Broadcast hanya dari master
        if addr == 0x00:
            return "TX"
        
        # Reserved address
        if addr > 0xF7:
            return None
        
        # Error response dari slave
        if func & 0x80:
            return "RX"
        
        # Valid function codes
        READ_FUNCS = [0x01, 0x02, 0x03, 0x04]
        WRITE_SINGLE = [0x05, 0x06]
        WRITE_MULTI = [0x0F, 0x10]
        
        if func not in (READ_FUNCS + WRITE_SINGLE + WRITE_MULTI + [0x17]):
            return None
        
        # Read functions
        if func in READ_FUNCS:
            if len(data) == 8:
                return "TX"  # Read request
            elif len(data) > 8:
                byte_count = data[2] if len(data) > 2 else 0
                expected = 3 + byte_count + 2
                if len(data) == expected:
                    return "RX"  # Read response
        
        # Write multiple
        if func in WRITE_MULTI:
            if len(data) == 8:
                return "RX"  # Response
            elif len(data) > 8:
                return "TX"  # Request
        
        return None
    
    def _detect_rs485_hardware_aware(self, data, port_name, conn_info):
        """
        RS-485 detection berdasarkan MAX485 hardware behavior
        
        MAX485 (dari schematic):
        - RE' (pin 2): Receiver Enable (active LOW)
        - DE (pin 3): Driver Enable (active HIGH)
        - Half-duplex enforced oleh hardware
        
        Detection methods:
        1. Error bit (100% accurate)
        2. Packet structure analysis
        3. Timing pattern (master poll → slave response)
        4. Size heuristic
        5. Alternating (hardware enforced)
        """
        
        if len(data) < 2:
            return "TX"
        
        current_time = time.time()
        
        # Method 1: Error bit (definitive)
        func_code = data[1]
        if func_code & 0x80:
            self.last_packet_time[port_name] = current_time
            return "RX"  # Slave error response
        
        # Method 2: Packet structure
        structure_result = self._analyze_rs485_packet_structure(data)
        if structure_result:
            self.last_packet_time[port_name] = current_time
            return structure_result
        
        # Method 3: Timing analysis
        if port_name in self.last_packet_time:
            gap = current_time - self.last_packet_time[port_name]
            
            if gap < 0.1:  # < 100ms → quick slave response
                self.last_packet_time[port_name] = current_time
                return "RX"
            elif gap > 0.5:  # > 500ms → new master request
                self.last_packet_time[port_name] = current_time
                return "TX"
        
        # Method 4: Size heuristic
        packet_len = len(data)
        size_hint = "TX" if packet_len <= 8 else "RX"
        
        # Method 5: Alternating (hardware half-duplex)
        last_dir = self.last_direction.get(f'rs485_{port_name}', "RX")
        
        # Combine size hint dengan alternating
        if size_hint == "TX" and last_dir == "RX":
            new_dir = "TX"
        elif size_hint == "RX" and last_dir == "TX":
            new_dir = "RX"
        else:
            new_dir = "RX" if last_dir == "TX" else "TX"
        
        self.last_direction[f'rs485_{port_name}'] = new_dir
        self.last_packet_time[port_name] = current_time
        
        return new_dir
    
    def _detect_by_pattern(self, data):
        """Pattern recognition untuk RS-232/RS-422"""
        if len(data) == 0:
            return None
        
        try:
            text = data.decode('ascii', errors='ignore').upper()
            
            # TX patterns
            tx_patterns = ['AT+', 'AT', 'GET', 'POST', 'SET', 'READ', 'WRITE', '$', '?']
            for pattern in tx_patterns:
                if text.startswith(pattern):
                    return "TX"
            
            # RX patterns
            rx_patterns = ['OK', 'ERROR', '+', 'HTTP/', '200', '404']
            for pattern in rx_patterns:
                if text.startswith(pattern):
                    return "RX"
        except:
            pass
        
        # Binary patterns
        first_byte = data[0]
        if first_byte < 0x20:
            return "TX"
        elif first_byte > 0x80:
            return "RX"
        
        return None
    
    def _detect_by_size(self, port_name, data):
        """Size-based detection dengan adaptive learning"""
        if port_name not in self.packet_history:
            self.packet_history[port_name] = []
        
        self.packet_history[port_name].append(len(data))
        
        if len(self.packet_history[port_name]) > 20:
            self.packet_history[port_name] = self.packet_history[port_name][-20:]
        
        if len(self.packet_history[port_name]) < 4:
            return "TX" if len(data) < 64 else "RX"
        
        avg_size = sum(self.packet_history[port_name]) / len(self.packet_history[port_name])
        return "TX" if len(data) < avg_size else "RX"
    
    def detect_direction_smart(self, port_name, port_type, detection_mode, data, conn_info):
        """
        Smart detection dengan per-port configuration
        
        Args:
            port_name: Nama port
            port_type: RS232/RS422/RS485
            detection_mode: Mode detection untuk port ini
            data: Data packet
            conn_info: Full connection info
            
        Returns:
            'TX' atau 'RX'
        """
        
        # Mode 'none' - all RX
        if detection_mode == 'none':
            return "RX"
        
        # Mode 'alternating' - simple toggle
        if detection_mode == 'alternating':
            current = self.last_direction[port_name]
            new_dir = "RX" if current == "TX" else "TX"
            self.last_direction[port_name] = new_dir
            return new_dir
        
        # Mode 'pattern' - pattern recognition
        if detection_mode == 'pattern':
            result = self._detect_by_pattern(data)
            if result:
                return result
            # Fallback to alternating
            current = self.last_direction[port_name]
            new_dir = "RX" if current == "TX" else "TX"
            self.last_direction[port_name] = new_dir
            return new_dir
        
        # Mode 'size' - size-based
        if detection_mode == 'size':
            return self._detect_by_size(port_name, data)
        
        # Mode 'rs485' - RS-485 specific (hardware-aware)
        if detection_mode == 'rs485' or port_type == 'RS485':
            return self._detect_rs485_hardware_aware(data, port_name, conn_info)
        
        # Mode 'auto' - smart combination
        if detection_mode == 'auto':
            # RS-485: use hardware-aware detection
            if port_type == 'RS485':
                return self._detect_rs485_hardware_aware(data, port_name, conn_info)
            
            # RS-232/RS-422: combine pattern + size
            pattern_result = self._detect_by_pattern(data)
            size_result = self._detect_by_size(port_name, data)
            
            if pattern_result == size_result and pattern_result is not None:
                self.last_direction[port_name] = pattern_result
                return pattern_result
            
            # Fallback: alternating
            current = self.last_direction[port_name]
            new_dir = "RX" if current == "TX" else "TX"
            self.last_direction[port_name] = new_dir
            return new_dir
        
        # Default: alternating
        current = self.last_direction[port_name]
        new_dir = "RX" if current == "TX" else "TX"
        self.last_direction[port_name] = new_dir
        return new_dir
    
    def display_data(self, conn_info, data, timestamp, direction):
        """Display data ke console"""
        label = conn_info['label']
        port = conn_info['port']
        port_type = conn_info.get('type', 'RS232')
        color = self.colors[conn_info['color']]
        
        # Update stats
        self.stats[port]['bytes'] += len(data)
        self.stats[port]['packets'] += 1
        if direction == "TX":
            self.stats[port]['tx'] += 1
            self.stats[port]['tx_bytes'] += len(data)
        else:
            self.stats[port]['rx'] += 1
            self.stats[port]['rx_bytes'] += len(data)
        
        # Header
        arrow = "→" if direction == "TX" else "←"
        print(f"{color}{self.colors['bold']}{'─'*80}{self.colors['reset']}")
        print(f"{color}[{timestamp}] {label} ({port}) [{port_type}] {arrow} {direction} | "
              f"Len: {len(data)}B{self.colors['reset']}")
        
        # Data
        if self.display_mode == 'hex':
            print(f"{color}HEX:   {self.format_hex(data)}{self.colors['reset']}")
        elif self.display_mode == 'ascii':
            print(f"{color}ASCII: {self.format_ascii(data)}{self.colors['reset']}")
        elif self.display_mode == 'both':
            hex_data, ascii_data = self.format_mixed(data)
            print(f"{color}HEX:   {hex_data}{self.colors['reset']}")
            print(f"{color}ASCII: {ascii_data}{self.colors['reset']}")
        
        print()
    
    def write_to_log(self, conn_info, data, timestamp, direction):
        """Write ke log file"""
        if not self.log_file:
            return
        
        try:
            with open(self.log_file, 'a') as f:
                if self.log_format == 'ascii':
                    data_str = self.format_ascii(data)
                else:
                    data_str = self.format_hex(data)
                
                # Include port label in log
                label = conn_info['label']
                f.write(f"{label} | {direction} : {timestamp} {data_str}\n")
        except Exception as e:
            print(f"{self.colors['red']}Error writing to log: {e}{self.colors['reset']}")
    
    def flush_packet_buffer(self, port_name, conn_info):
        """Flush complete packet"""
        with self.buffer_lock:
            if port_name in self.packet_buffer and len(self.packet_buffer[port_name]) > 0:
                complete_packet = bytes(self.packet_buffer[port_name])
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                
                # Detect direction dengan per-port config
                port_type = conn_info.get('type', 'RS232')
                detection_mode = conn_info.get('detection', 'auto')
                
                direction = self.detect_direction_smart(
                    port_name, port_type, detection_mode, complete_packet, conn_info
                )
                
                self.display_data(conn_info, complete_packet, timestamp, direction)
                
                if self.log_file:
                    self.write_to_log(conn_info, complete_packet, timestamp, direction)
                
                self.packet_buffer[port_name] = bytearray()
    
    def read_port(self, conn_info):
        """Thread untuk baca port dengan per-port packet timeout"""
        conn = conn_info['serial']
        port = conn_info['port']
        packet_timeout = conn_info.get('packet_timeout', 0.05)
        
        while self.running:
            try:
                if conn.in_waiting > 0:
                    chunk = conn.read(conn.in_waiting)
                    current_time = time.time()
                    
                    with self.buffer_lock:
                        if port in self.last_receive_time:
                            time_gap = current_time - self.last_receive_time[port]
                            
                            if time_gap > packet_timeout:
                                if len(self.packet_buffer[port]) > 0:
                                    self.flush_packet_buffer(port, conn_info)
                        
                        self.packet_buffer[port].extend(chunk)
                        self.last_receive_time[port] = current_time
                
                # Check timeout flush
                current_time = time.time()
                if port in self.last_receive_time:
                    time_since_last = current_time - self.last_receive_time[port]
                    if time_since_last > packet_timeout and len(self.packet_buffer[port]) > 0:
                        self.flush_packet_buffer(port, conn_info)
                
                time.sleep(0.001)
                
            except serial.SerialException as e:
                print(f"{self.colors['red']}ERROR reading from {conn_info['label']}: {e}{self.colors['reset']}")
                break
            except Exception as e:
                print(f"{self.colors['red']}Unexpected error on {conn_info['label']}: {e}{self.colors['reset']}")
                break
    
    def print_statistics(self):
        """Print statistics"""
        print("\n" + "="*80)
        print("  COMMUNICATION STATISTICS")
        print("="*80)
        
        for conn in self.serial_connections:
            port = conn['port']
            label = conn['label']
            port_type = conn.get('type', 'RS232')
            detection = conn.get('detection', 'auto')
            stats = self.stats[port]
            
            print(f"  {label:<30} ({port})")
            print(f"    Type: {port_type} | Detection: {detection}")
            print(f"    Config: {conn['baudrate']} {conn['bytesize']}{conn['parity']}{conn['stopbits']}")
            print(f"    Packets: {stats['packets']} ({stats['bytes']} bytes)")
            
            if detection != 'none':
                print(f"    TX: {stats['tx']} pkts ({stats['tx_bytes']} bytes) | "
                      f"RX: {stats['rx']} pkts ({stats['rx_bytes']} bytes)")
            print()
        
        print("="*80 + "\n")
    
    def start_tapping(self):
        """Start monitoring"""
        self.running = True
        
        print("\n" + "="*80)
        print(f"  {self.colors['bold']}SERIAL PORT TAPPER v5.0 - MONITORING ACTIVE{self.colors['reset']}")
        print("="*80)
        print(f"  Display Mode: {self.display_mode.upper()}")
        
        if self.log_file:
            print(f"  Log File: {self.log_file} | Format: {self.log_format.upper()}")
        
        print(f"  Monitoring {len(self.serial_connections)} port(s) with individual configs:")
        
        for conn in self.serial_connections:
            print(f"    • {conn['label']} @ {conn['baudrate']} baud [{conn['type']}] "
                  f"- Detection: {conn['detection']}, Timeout: {conn['packet_timeout']*1000:.0f}ms")
        
        print(f"\n  {self.colors['yellow']}Press Ctrl+C to stop{self.colors['reset']}")
        print("="*80 + "\n")
        
        # Create threads
        for conn_info in self.serial_connections:
            thread = threading.Thread(
                target=self.read_port,
                args=(conn_info,),
                daemon=True,
                name=f"Tapper-{conn_info['port']}"
            )
            thread.start()
            self.threads.append(thread)
        
        try:
            while self.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print(f"\n\n{self.colors['yellow']}Stopping...{self.colors['reset']}")
            self.stop_tapping()
    
    def stop_tapping(self):
        """Stop monitoring"""
        self.running = False
        
        for port in list(self.packet_buffer.keys()):
            for conn in self.serial_connections:
                if conn['port'] == port:
                    self.flush_packet_buffer(port, conn)
                    break
        
        for thread in self.threads:
            thread.join(timeout=1)
        
        self.print_statistics()
        self.close_connections()
        
        if self.log_file:
            print(f"Log saved: {self.log_file}\n")


def expand_log_variables(log_path):
    """Expand variables dalam log path"""
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


def parse_port_config(port_str):
    """
    Parse port configuration string
    
    Format: port[:label[:baudrate[:bytesize[:parity[:stopbits[:type[:detection[:timeout]]]]]]]]
    
    Examples:
        /dev/ttyACM1
        /dev/ttyACM1:Device1
        /dev/ttyACM1:Device1:9600
        /dev/ttyACM1:Device1:9600:8:N:1:RS232:auto:50
    """
    parts = port_str.split(':')
    
    config = {
        'port': parts[0].strip()
    }
    
    if len(parts) >= 2:
        config['label'] = parts[1].strip()
    else:
        config['label'] = parts[0].strip().split('/')[-1]
    
    if len(parts) >= 3:
        config['baudrate'] = int(parts[2].strip())
    
    if len(parts) >= 4:
        config['bytesize'] = int(parts[3].strip())
    
    if len(parts) >= 5:
        config['parity'] = parts[4].strip().upper()
    
    if len(parts) >= 6:
        config['stopbits'] = float(parts[5].strip())
    
    if len(parts) >= 7:
        config['type'] = parts[6].strip().upper()
    
    if len(parts) >= 8:
        config['detection'] = parts[7].strip().lower()
    
    if len(parts) >= 9:
        config['packet_timeout'] = int(parts[8].strip()) / 1000.0
    
    return config


def main():
    parser = argparse.ArgumentParser(
        description='Serial Port Tapper v5.0 - Ultimate Edition',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
FULL PER-PORT CONFIGURATION FORMAT:
  port:label:baud:data:parity:stop:type:detection:timeout

  port       - /dev/ttyACM1 (required)
  label      - MyDevice (optional, default: port name)
  baud       - 9600 (optional, default: 9600)
  data       - 8 (optional, default: 8)
  parity     - N/E/O (optional, default: N)
  stop       - 1/1.5/2 (optional, default: 1)
  type       - RS232/RS422/RS485 (optional, default: RS232)
  detection  - auto/alternating/pattern/size/rs485/none (optional, default: auto)
  timeout    - 50 (ms) (optional, default: 50)

EXAMPLES:

1. Simple (use defaults):
   ./serial_tapper.py -p /dev/ttyACM1

2. With custom baudrate:
   ./serial_tapper.py -p /dev/ttyACM1:Device1:115200

3. Full RS-232 config:
   ./serial_tapper.py -p /dev/ttyACM1:Debug:115200:8:N:1:RS232:auto:50

4. RS-485 Modbus:
   ./serial_tapper.py -p /dev/ttyUSB0:Modbus:19200:8:E:1:RS485:rs485:30

5. Mixed - 3 ports, all different:
   ./serial_tapper.py \\
     -p /dev/ttyACM1:RS232Debug:115200:8:N:1:RS232:pattern:50 \\
     -p /dev/ttyACM2:SlowSensor:9600:8:N:1:RS232:auto:100 \\
     -p /dev/ttyUSB0:ModbusRTU:19200:8:E:1:RS485:rs485:30

PORT TYPES:
  RS232  - Standard point-to-point
  RS422  - Differential signaling
  RS485  - Multi-drop network (hardware-aware detection)

DETECTION MODES:
  auto        - Smart (recommended)
  rs485       - RS-485/Modbus specific (hardware-aware)
  pattern     - Pattern recognition
  size        - Size-based
  alternating - Simple toggle
  none        - All RX

LOG FILE VARIABLES:
  {date}, {time}, {datetime}, {timestamp}
        """
    )
    
    parser.add_argument('-p', '--port', action='append', dest='ports',
                        help='Port config (full format or simple)')
    
    parser.add_argument('-d', '--display', dest='display_mode',
                        choices=['hex', 'ascii', 'both'], default='both',
                        help='Display mode (default: both)')
    
    parser.add_argument('-l', '--log', dest='log_file',
                        help='Log file path (supports variables)')
    
    parser.add_argument('--log-format', dest='log_format',
                        choices=['hex', 'ascii'], default='hex',
                        help='Log format (default: hex)')
    
    parser.add_argument('--list', action='store_true',
                        help='List available ports')
    
    args = parser.parse_args()
    
    if args.list:
        tapper = SerialTapper([])
        tapper.list_available_ports()
        return
    
    if not args.ports:
        print(f"\n{ColorText.RED}Error: At least 1 port required!{ColorText.RESET}\n")
        parser.print_help()
        sys.exit(1)
    
    # Parse port configs
    tap_ports = []
    for port_str in args.ports:
        config = parse_port_config(port_str)
        tap_ports.append(config)
    
    # Process log file
    log_file = None
    if args.log_file:
        log_file = expand_log_variables(args.log_file)
        if not log_file.endswith('.txt'):
            log_file = f"{log_file}.txt"
        print(f"\n{ColorText.GREEN}Log file: {log_file}{ColorText.RESET}")
    
    # Create and start
    try:
        tapper = SerialTapper(
            tap_ports=tap_ports,
            log_file=log_file,
            display_mode=args.display_mode,
            log_format=args.log_format
        )
        
        tapper.list_available_ports()
        tapper.open_connections()
        tapper.start_tapping()
        
    except KeyboardInterrupt:
        print("\n\nInterrupted")
    except Exception as e:
        print(f"\n{ColorText.RED}Error: {e}{ColorText.RESET}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)


class ColorText:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RESET = '\033[0m'


if __name__ == '__main__':
    main()