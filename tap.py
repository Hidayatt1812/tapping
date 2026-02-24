#!/usr/bin/env python3
import argparse
import time
import threading
import queue
from datetime import datetime

import serial


def ts_now():
    now = datetime.now()
    return now.strftime("%H:%M:%S.") + f"{int(now.microsecond / 1000):03d}"


def bytes_to_text(data: bytes, mode: str) -> str:
    if mode == "hex":
        return data.hex(" ").upper()

    out = []
    for b in data:
        if 32 <= b <= 126:
            out.append(chr(b))
        elif b == 10:
            out.append("\\n")
        elif b == 13:
            out.append("\\r")
        else:
            out.append(f"\\x{b:02X}")
    return "".join(out)


def safe_put(q: queue.Queue, msg: str):
    try:
        q.put(msg, timeout=0.2)
    except queue.Full:
        # Drop to avoid hang if disk/console is slow
        pass


def reader(label: str, port: str, baud: int, serial_params: dict, mode: str,
           out_q: queue.Queue, stop_evt: threading.Event,
           reconnect_delay: float, read_sleep: float):
    """
    Non-blocking reader with auto-reconnect.
    Output: TAP <label>: <timestamp> <data>
    """
    while not stop_evt.is_set():
        ser = None
        try:
            ser = serial.Serial(port=port, baudrate=baud, timeout=0, **serial_params)
            try:
                ser.reset_input_buffer()
            except Exception:
                pass

            safe_put(out_q, f"TAP {label}: {ts_now()} INFO connected {port} @ {baud}")

            while not stop_evt.is_set():
                data = ser.read(4096)
                if data:
                    line = f"TAP {label}: {ts_now()} {bytes_to_text(data, mode)}"
                    safe_put(out_q, line)
                else:
                    time.sleep(read_sleep)

        except Exception as e:
            safe_put(out_q, f"TAP {label}: {ts_now()} ERROR {port}: {e}")
            time.sleep(reconnect_delay)
        finally:
            if ser:
                try:
                    ser.close()
                except Exception:
                    pass


def writer(outfile: str, out_q: queue.Queue, stop_evt: threading.Event, also_print: bool):
    with open(outfile, "a", encoding="utf-8") as f:
        while not stop_evt.is_set() or not out_q.empty():
            try:
                line = out_q.get(timeout=0.2)
            except queue.Empty:
                continue
            f.write(line + "\n")
            f.flush()
            if also_print:
                print(line, flush=True)


def parse_port_specs(specs):
    """
    specs example:
      ["TAP1=/dev/ttyS3@57600", "TAP2=/dev/ttyS4@19200"]
      or ["=/dev/ttyS3@57600"] (label auto)
      or ["/dev/ttyS3@57600"]  (label auto)
      or ["TAP1=/dev/ttyS3"]   (baud default)
    returns list of (label, port, baud or None)
    """
    out = []
    auto_i = 1

    for s in specs:
        s = s.strip()
        label = None
        port_part = s

        if "=" in s:
            left, right = s.split("=", 1)
            if left.strip():
                label = left.strip()
            port_part = right.strip()

        if "@" in port_part:
            port, baud_s = port_part.split("@", 1)
            port = port.strip()
            baud = int(baud_s.strip())
        else:
            port = port_part.strip()
            baud = None

        if not label:
            label = f"TAP{auto_i}"
            auto_i += 1

        if not port:
            raise ValueError(f"Port kosong pada spec: {s}")

        out.append((label, port, baud))

    return out


def main():
    ap = argparse.ArgumentParser(
        description="Flexible multi-port serial TAP logger (1,2,3,... ports) with ms timestamp, non-blocking, auto-reconnect."
    )
    ap.add_argument(
        "--port",
        action="append",
        required=True,
        help=("Port spec (repeatable). Format: "
              "'LABEL=/dev/ttyS3@57600' atau '/dev/ttyS3@57600' atau 'LABEL=/dev/ttyS3'. "
              "Bisa dipakai berkali-kali: --port ... --port ...")
    )

    ap.add_argument("--baud-default", type=int, default=19200, help="Default baud kalau tidak ditulis @ (default 19200)")
    ap.add_argument("--out", default="tap_multi.txt", help="Output TXT (append). Default tap_multi.txt")
    ap.add_argument("--mode", choices=["hex", "ascii"], default="hex", help="Payload format: hex/ascii")
    ap.add_argument("--no-print", action="store_true", help="Kalau diaktifkan, tidak print ke terminal (hanya file)")
    ap.add_argument("--queue-max", type=int, default=30000, help="Max log queue (anti hang). Default 30000")
    ap.add_argument("--reconnect-delay", type=float, default=1.0, help="Delay reconnect detik. Default 1.0")
    ap.add_argument("--read-sleep-ms", type=float, default=1.0, help="Sleep saat tidak ada data (ms). Default 1.0")

    ap.add_argument("--bytesize", type=int, choices=[5, 6, 7, 8], default=8, help="Data bits (default 8)")
    ap.add_argument("--parity", choices=["N", "E", "O", "M", "S"], default="N", help="Parity (default N)")
    ap.add_argument("--stopbits", choices=[1, 2], type=int, default=1, help="Stop bits (default 1)")

    args = ap.parse_args()

    port_specs = parse_port_specs(args.port)

    parity_map = {
        "N": serial.PARITY_NONE,
        "E": serial.PARITY_EVEN,
        "O": serial.PARITY_ODD,
        "M": serial.PARITY_MARK,
        "S": serial.PARITY_SPACE,
    }
    bytesize_map = {
        5: serial.FIVEBITS,
        6: serial.SIXBITS,
        7: serial.SEVENBITS,
        8: serial.EIGHTBITS,
    }
    stopbits_map = {1: serial.STOPBITS_ONE, 2: serial.STOPBITS_TWO}

    serial_params = {
        "bytesize": bytesize_map[args.bytesize],
        "parity": parity_map[args.parity],
        "stopbits": stopbits_map[args.stopbits],
    }

    out_q = queue.Queue(maxsize=args.queue_max)
    stop_evt = threading.Event()

    t_writer = threading.Thread(
        target=writer,
        args=(args.out, out_q, stop_evt, not args.no_print),
        daemon=True
    )
    t_writer.start()

    threads = [t_writer]

    read_sleep = max(args.read_sleep_ms, 0.0) / 1000.0

    for label, port, baud in port_specs:
        b = baud if baud is not None else args.baud_default
        t = threading.Thread(
            target=reader,
            args=(label, port, b, serial_params, args.mode, out_q, stop_evt,
                  args.reconnect_delay, read_sleep),
            daemon=True
        )
        t.start()
        threads.append(t)

    print(f"Logging => {args.out}")
    print("Ports:")
    for label, port, baud in port_specs:
        b = baud if baud is not None else args.baud_default
        print(f"  - {label}: {port} @ {b}")
    print("\nCtrl+C untuk stop.\n")

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        stop_evt.set()
        time.sleep(0.5)


if __name__ == "__main__":
    main()