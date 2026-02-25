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
# Baudrate sama untuk semua port
python serial_tapper.py -p /dev/ttyACM1 -b 115200

# Baudrate BERBEDA per-port
python serial_tapper.py -p /dev/ttyACM1:Dev1:9600 -p /dev/ttyACM2:Dev2:115200

# Monitor 4 port dengan baudrate berbeda-beda
python serial_tapper.py \
  -p /dev/ttyACM0:Sensor1:9600 \
  -p /dev/ttyACM1:Sensor2:19200 \
  -p /dev/ttyS3:Gateway:115200 \
  -p /dev/ttyUSB0:Device:38400
```

**Format Port dengan Baudrate:**
```
/dev/ttyACM1              -> Baudrate default (9600)
/dev/ttyACM1:MyDevice     -> Baudrate default, dengan label
/dev/ttyACM1:MyDevice:115200 -> Baudrate custom per-port
```

**Kombinasi Default dan Custom:**
```bash
# Port1 dan Port3 pakai 9600, Port2 pakai 115200
python serial_tapper.py \
  -b 9600 \
  -p /dev/ttyACM1:Port1 \
  -p /dev/ttyACM2:Port2:115200 \
  -p /dev/ttyS3:Port3
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

Simpan semua komunikasi ke file log dalam format TXT:

```bash
# Log dengan nama file custom
python serial_tapper.py -p /dev/ttyACM1 -l my_custom_log.txt

# Log dengan nama file dinamis (auto timestamp)
python serial_tapper.py -p /dev/ttyACM1 -l tapping_{datetime}.txt

# Hasil: tapping_20250225_103045.txt

# Log dengan format ASCII
python serial_tapper.py -p /dev/ttyACM1 -l data_{date}.txt --log-format ascii

# Hasil: data_20250225.txt
```

**Variables untuk Nama File Dinamis:**

| Variable | Format | Contoh Output |
|----------|--------|---------------|
| `{date}` | YYYYMMDD | 20250225 |
| `{time}` | HHMMSS | 103045 |
| `{datetime}` | YYYYMMDD_HHMMSS | 20250225_103045 |
| `{timestamp}` | Unix timestamp | 1708851045 |

**Contoh Penggunaan:**
```bash
# Nama file dengan tanggal
python serial_tapper.py -p /dev/ttyACM1 -l capture_{date}.txt

# Nama file dengan tanggal dan waktu
python serial_tapper.py -p /dev/ttyACM1 -l log_{datetime}.txt

# Nama file dengan unix timestamp
python serial_tapper.py -p /dev/ttyACM1 -l data_{timestamp}.txt

# Kombinasi custom dengan variable
python serial_tapper.py -p /dev/ttyACM1 -l monitoring_acm1_{date}_session.txt
```

**Format Log File:**
```
RX : 2025-02-25 10:30:45.123 48 65 6C 6C 6F 20 57 6F 72 6C 64
TX : 2025-02-25 10:30:45.456 4F 4B 0D 0A
```

**Penjelasan Format:**
- `RX` = Data yang diterima (Receive)
- `TX` = Data yang dikirim (Transmit)
- Timestamp format: `YYYY-MM-DD HH:MM:SS.mmm`
- Data dalam format HEX atau ASCII (tergantung parameter `--log-format`)
- Extension `.txt` otomatis ditambahkan jika belum ada

### 8. Complete Example

**Contoh 1: Semua port pakai baudrate sama**

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
  -l monitoring_{datetime}.txt \
  --log-format hex
```

**Hasil nama file log:** `monitoring_20250225_103045.txt`

**Contoh 2: Setiap port pakai baudrate berbeda**

```bash
python serial_tapper.py \
  -p /dev/ttyACM1:Sensor1:9600 \
  -p /dev/ttyACM2:Sensor2:19200 \
  -p /dev/ttyS3:Gateway:115200 \
  -p /dev/ttyUSB0:Device4:38400 \
  -d both \
  -l multi_baudrate_{datetime}.txt \
  --log-format hex
```

Output akan menampilkan baudrate untuk setiap port:
```
Monitoring 4 port(s):
  - Sensor1 (/dev/ttyACM1) @ 9600 baud
  - Sensor2 (/dev/ttyACM2) @ 19200 baud
  - Gateway (/dev/ttyS3) @ 115200 baud
  - Device4 (/dev/ttyUSB0) @ 38400 baud
```

**Contoh 3: Kombinasi default dan custom baudrate**

```bash
# Default 9600, kecuali Gateway pakai 115200
python serial_tapper.py \
  -b 9600 \
  -p /dev/ttyACM1:Sensor1 \
  -p /dev/ttyACM2:Sensor2 \
  -p /dev/ttyS3:Gateway:115200 \
  -l combined_{date}.txt
```

**Catatan Penting:**
- Parameter `-d` (display mode) mengatur tampilan di console (hex/ascii/both)
- Parameter `--log-format` mengatur format data di log file (hex/ascii)
- Keduanya bisa berbeda, misal: tampilan console `both`, log file `hex`
- Gunakan variables `{date}`, `{time}`, `{datetime}`, atau `{timestamp}` untuk nama file dinamis
- Extension `.txt` otomatis ditambahkan jika belum ada
- **Setiap port bisa punya baudrate berbeda** dengan format: `port:label:baudrate`
- Port tanpa baudrate akan menggunakan default baudrate dari parameter `-b`

## Skenario Penggunaan Anda

Berdasarkan kebutuhan Anda untuk tapping yang **fleksibel dan dinamis**:

### Skenario 1: Tapping Single Port
```bash
# Tapping ACM1 @ 9600 baud
python serial_tapper.py -p /dev/ttyACM1:TappingPort:9600

# Tapping ACM1 @ 115200 baud
python serial_tapper.py -p /dev/ttyACM1:TappingPort:115200
```

### Skenario 2: Tapping 2 Port dengan Baudrate Berbeda
```bash
# ACM1 @ 9600, ttyS3 @ 115200
python serial_tapper.py \
  -p /dev/ttyACM1:Monitor1:9600 \
  -p /dev/ttyS3:Gateway:115200 \
  -l tap_2ports_{datetime}.txt
```

### Skenario 3: Tapping 3 Port dengan Baudrate Berbeda
```bash
python serial_tapper.py \
  -p /dev/ttyACM1:DeviceA:9600 \
  -p /dev/ttyACM2:DeviceB:19200 \
  -p /dev/ttyS3:Gateway:115200 \
  -l tap_3ports_{datetime}.txt
```

### Skenario 4: Tapping 4+ Port (Fully Dynamic)
```bash
# Contoh dengan 4 port, baudrate semua berbeda
python serial_tapper.py \
  -p /dev/ttyACM0:Sensor1:9600 \
  -p /dev/ttyACM1:Sensor2:19200 \
  -p /dev/ttyACM2:Controller:115200 \
  -p /dev/ttyS3:Gateway:38400 \
  -d both \
  -l monitoring_all_{datetime}.txt

# Bisa ditambah lagi sesuai kebutuhan
# -p /dev/ttyUSB0:Device5:57600 \
# -p /dev/ttyUSB1:Device6:9600 \
```

### Skenario 5: Mix Default dan Custom Baudrate
```bash
# Default 9600, kecuali Gateway dan Controller
python serial_tapper.py \
  -b 9600 \
  -p /dev/ttyACM1:Sensor1 \
  -p /dev/ttyACM2:Sensor2 \
  -p /dev/ttyS3:Gateway:115200 \
  -p /dev/ttyUSB0:Controller:38400 \
  -l mixed_baudrate_{date}.txt
```
(Sensor1 dan Sensor2 pakai 9600, Gateway pakai 115200, Controller pakai 38400)

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
                    Format:
                    - /dev/ttyACM1 (baudrate default)
                    - /dev/ttyACM1:Label (baudrate default, dengan label)
                    - /dev/ttyACM1:Label:9600 (baudrate custom per-port)

-b, --baudrate      Default baud rate untuk semua port (default: 9600)
                    Bisa di-override per-port dengan format port:label:baudrate
                    Common: 9600, 19200, 38400, 57600, 115200

--bytesize          Data bits: 5, 6, 7, 8 (default: 8)

--parity            Parity check
                    N: None (default)
                    E: Even
                    O: Odd
                    M: Mark
                    S: Space

--stopbits          Stop bits: 1, 1.5, 2 (default: 1)

-d, --display       Display mode untuk CONSOLE
                    hex: Tampilkan dalam format HEX
                    ascii: Tampilkan dalam format ASCII
                    both: Tampilkan HEX dan ASCII (default)

-l, --log           Path file untuk logging dalam format TXT (optional)
                    Mendukung variables untuk nama dinamis:
                    {date} {time} {datetime} {timestamp}
                    Contoh: tapping_{datetime}.txt

--log-format        Format data di LOG FILE
                    hex: Format HEX (default)
                    ascii: Format ASCII

--list              List semua available serial ports
```

## Output Format

### Console Output

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

### Log File Format

Log file disimpan dalam format TXT sederhana dengan struktur:

**Format HEX (default):**
```
RX : 2025-02-25 10:30:45.123 48 65 6C 6C 6F 20 57 6F 72 6C 64 21 0D 0A
TX : 2025-02-25 10:30:45.456 4F 4B 0D 0A
RX : 2025-02-25 10:30:46.789 41 54 2B 43 47 4D 49 3D 31 0D
TX : 2025-02-25 10:30:47.012 2B 43 47 4D 49 3A 20 31 0D 0A
```

**Format ASCII:**
```
RX : 2025-02-25 10:30:45.123 Hello World![0D][0A]
TX : 2025-02-25 10:30:45.456 OK[0D][0A]
RX : 2025-02-25 10:30:46.789 AT+CGMI=1[0D]
TX : 2025-02-25 10:30:47.012 +CGMI: 1[0D][0A]
```

**Struktur Format:**
- `RX` atau `TX` : Indikator arah komunikasi
- Timestamp : `YYYY-MM-DD HH:MM:SS.mmm`
- Data : Dalam format HEX atau ASCII sesuai parameter `--log-format`

**Keuntungan Format Ini:**
- Mudah dibaca dan di-parse
- Bisa diedit manual dengan text editor
- Timestamp lengkap untuk analisis timing
- Jelas membedakan RX dan TX
- Format ringan dan efisien

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