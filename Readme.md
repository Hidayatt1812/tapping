# Serial Port Tapper

Program Python untuk monitoring dan tapping komunikasi serial port secara real-time. Mendukung RS-232, RS-422, dan RS-485.

## Fitur

✅ **Flexible Port Configuration** - Monitor 1 atau lebih port secara bersamaan
✅ **Dynamic Labeling** - Beri label custom untuk setiap port
✅ **Direction Detection** - Deteksi arah komunikasi (TX/RX)
✅ **Multiple Display Modes** - HEX, ASCII, atau keduanya
✅ **Color-coded Output** - Setiap port punya warna berbeda untuk kemudahan identifikasi
✅ **Logging Support** - Simpan semua data ke file log
✅ **Real-time Statistics** - Tracking packets dan bytes per port
✅ **Read-only** - Hanya membaca, tidak mengirim data (true tapping)

## Requirements

```bash
pip install pyserial
```

## Instalasi

1. Copy file `serial_tapper.py` ke direktori kerja Anda
2. Berikan permission untuk execute:
```bash
chmod +x serial_tapper.py
```

## Penggunaan

### 1. List Available Ports

Untuk melihat port serial yang tersedia:

```bash
python serial_tapper.py --list
```

atau

```bash
./serial_tapper.py --list
```

### 2. Monitor Single Port

Monitor satu port dengan konfigurasi default (9600 baud):

```bash
python serial_tapper.py -p /dev/ttyACM1
```

### 3. Monitor Multiple Ports

Monitor beberapa port sekaligus:

```bash
python serial_tapper.py -p /dev/ttyACM1 -p /dev/ttyACM2
```

### 4. Monitor dengan Label Custom

Beri label yang mudah diingat untuk setiap port:

```bash
python serial_tapper.py -p /dev/ttyACM1:DeviceA -p /dev/ttyACM2:DeviceB
```

atau untuk contoh Anda:

```bash
python serial_tapper.py -p /dev/ttyACM1:Tapping -p /dev/ttyS3:Gateway
```

### 5. Custom Baudrate

```bash
python serial_tapper.py -p /dev/ttyACM1 -b 115200
```

### 6. Display Mode

Pilih mode tampilan data:

```bash
# Hanya HEX
python serial_tapper.py -p /dev/ttyACM1 -d hex

# Hanya ASCII
python serial_tapper.py -p /dev/ttyACM1 -d ascii

# HEX dan ASCII (default)
python serial_tapper.py -p /dev/ttyACM1 -d both
```

### 7. Save to Log File

Simpan semua komunikasi ke file log:

```bash
python serial_tapper.py -p /dev/ttyACM1 -l tapping.log
```

### 8. Complete Example

Contoh lengkap dengan semua parameter:

```bash
python serial_tapper.py \
  -p /dev/ttyACM1:Device_A \
  -p /dev/ttyACM2:Device_B \
  -p /dev/ttyS3:Gateway \
  -b 115200 \
  --bytesize 8 \
  --parity N \
  --stopbits 1 \
  -d both \
  -l communication.log
```

## Skenario Penggunaan Anda

Berdasarkan ilustrasi Anda:
- `/dev/ttyACM0` ↔ `/dev/ttyACM2` saling komunikasi (loopback)
- `/dev/ttyACM1` untuk tapping

Untuk monitoring tapping di ACM1:

```bash
python serial_tapper.py -p /dev/ttyACM1:TappingPort -b 9600
```

Jika di real implementation Anda ingin tap ACM1 dan ttyS3:

```bash
python serial_tapper.py \
  -p /dev/ttyACM1:Monitor1 \
  -p /dev/ttyS3:Monitor2 \
  -b 9600 \
  -l realtime_tap.log
```

## Parameter Lengkap

```
-p, --port          Port untuk di-tap (bisa multiple)
                    Format: /dev/ttyACM1 atau /dev/ttyACM1:Label

-b, --baudrate      Baud rate (default: 9600)
                    Common: 9600, 19200, 38400, 57600, 115200

--bytesize          Data bits: 5, 6, 7, 8 (default: 8)

--parity            Parity check
                    N: None (default)
                    E: Even
                    O: Odd
                    M: Mark
                    S: Space

--stopbits          Stop bits: 1, 1.5, 2 (default: 1)

-d, --display       Display mode
                    hex: Tampilkan dalam format HEX
                    ascii: Tampilkan dalam format ASCII
                    both: Tampilkan HEX dan ASCII (default)

-l, --log           Path file untuk logging (optional)

--list              List semua available serial ports
```

## Output Format

Program akan menampilkan:

```
================================================================================
[2025-02-25 10:30:45.123] TappingPort (/dev/ttyACM1) → TX | Length: 16 bytes
HEX:   48 65 6C 6C 6F 20 57 6F 72 6C 64 21 0D 0A
ASCII: Hello World!..
================================================================================
```

Keterangan:
- **Timestamp**: Waktu penerimaan data dengan presisi milidetik
- **Label**: Label port yang Anda tentukan
- **Port**: Port fisik yang digunakan
- **Direction**: TX (transmit) atau RX (receive)
- **Length**: Jumlah bytes yang diterima
- **HEX**: Data dalam format hexadecimal
- **ASCII**: Data dalam format ASCII (karakter non-printable ditampilkan sebagai [XX])

## Statistics

Saat Anda stop monitoring (Ctrl+C), program akan menampilkan statistik:

```
================================================================================
  COMMUNICATION STATISTICS
================================================================================
  TappingPort                    (/dev/ttyACM1)
    Packets: 145       | Bytes: 2048
  Monitor2                       (/dev/ttyS3)
    Packets: 89        | Bytes: 1532
================================================================================
```

## Tips Penggunaan

1. **Permission Issues**: Jika ada error permission denied, tambahkan user ke dialout group:
   ```bash
   sudo usermod -a -G dialout $USER
   ```
   Kemudian logout dan login kembali.

2. **Check Port Availability**: Selalu gunakan `--list` terlebih dahulu untuk memastikan port yang ingin di-tap tersedia.

3. **Baudrate**: Pastikan baudrate yang Anda set sama dengan baudrate komunikasi yang sedang terjadi.

4. **Multiple Monitoring**: Anda bisa monitor sebanyak mungkin port sesuai kebutuhan, program akan membuat thread terpisah untuk masing-masing.

5. **Log File**: Untuk analisis lebih lanjut, gunakan parameter `-l` untuk menyimpan semua data ke file.

## Troubleshooting

**Port sudah digunakan (busy)**
```
Error: Device or resource busy
```
- Pastikan tidak ada program lain yang menggunakan port tersebut
- Close aplikasi seperti minicom, screen, atau tapper lain

**Port not found**
```
Error: [Errno 2] No such file or directory: '/dev/ttyACM1'
```
- Port tidak terhubung atau tidak tersedia
- Gunakan `--list` untuk melihat port yang tersedia

**Permission denied**
```
Error: [Errno 13] Permission denied: '/dev/ttyACM1'
```
- User tidak punya akses ke serial port
- Tambahkan user ke group dialout (lihat Tips di atas)

## Cara Kerja

Program ini bekerja dengan cara:
1. Membuka koneksi serial dalam mode **read-only**
2. Membuat thread terpisah untuk setiap port yang di-monitor
3. Setiap thread terus-menerus membaca buffer input
4. Ketika ada data masuk, langsung ditampilkan dengan timestamp
5. Direction (TX/RX) dideteksi berdasarkan timing pattern antar packet

**CATATAN PENTING**: Program ini hanya MEMBACA data yang lewat di port. Tidak ada data yang dikirim atau dimodifikasi. Ini adalah true passive tapping.

## License

Free to use and modify.

## Author

Created for serial port monitoring and debugging purposes.