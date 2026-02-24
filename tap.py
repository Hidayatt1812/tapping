#!/usr/bin/env python3
import argparse
import time
import threading
import queue
from datetime import datetime
import serial


def ts_now():
    now = datetime.now()
    return now.strftime("%H:%M:%S.") + f"{int(now.microsecond/1000):03d}"


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


def split_with_dir_markers(buf: bytes):
    """
    Kalau stream mengandung marker arah ASCII, kita pecah jadi event berlabel.
    Marker yang didukung (case-insensitive):
      - b'RX:'  => FRX
      - b'TX:'  => FTX

    Kalau tidak ada marker, return 1 event 'F??' (unknown direction).
    """
    up = buf.upper()

    # jika tidak ada marker sama sekali
    if b"RX:" not in up and b"TX:" not in up:
        return [("F??", buf)]

    # parsing sederhana: cari semua marker dan ambil segmen setelahnya sampai marker berikutnya
    events = []
    i = 0
    while i < len(buf):
        up = buf.upper()
        rx_pos = up.find(b"RX:", i)
        tx_pos = up.find(b"TX:", i)

        # cari marker terdekat
        candidates = [(rx_pos, "FRX"), (tx_pos, "FTX")]
        candidates = [(pos, lab) for pos, lab in candidates if pos != -1]
        if not candidates:
            # sisa data tanpa marker -> lekatkan ke event terakhir kalau ada
            if events:
                lab, prev = events[-1]
                events[-1] = (lab, prev + buf[i:])
            else:
                events.append(("F??", buf[i:]))
            break

        pos, lab = min(candidates, key=lambda x: x[0])

        # data sebelum marker -> lekatkan ke event sebelumnya
        if pos > i:
            if events:
                elab, prev = events[-1]
                events[-1] = (elab, prev + buf[i:pos])
            else:
                events.append(("F??", buf[i:pos]))

        # lompat lewat marker
        j = pos + 3  # len("RX:") / len("TX:")
        # cari marker berikutnya
        up2 = buf.upper()
        next_rx = up2.find(b"RX:", j)
        next_tx = up2.find(b"TX:", j)
        next_candidates = [p for p in [next_rx, next_tx] if p != -1]
        end = min(next_candidates) if next_candidates else len(buf)

        payload = buf[j:end]
        if payload:
            events.append((lab, payload))
        i = end

    # buang event kosong
    events = [(lab, p) for lab, p in events if p]
    return events if events else [("F??", buf)]


def serial_reader_fcc(port, baud, bytesize, parity, stopbits, mode,
                      out_q, stop_evt, reopen_delay=1.0, timeout=0.1):
    """
    FCC RS232 tap reader.
    - Kalau ada marker RX:/TX: -> output FRX/FTX
    - Kalau tidak -> output F?? (unknown direction)
    """
    while not stop_evt.is_set():
        ser = None
        try:
            ser = serial.Serial(port=port, baudrate=baud, bytesize=bytesize,
                                parity=parity, stopbits=stopbits, timeout=timeout)
            try:
                ser.reset_input_buffer()
            except Exception:
                pass

            out_q.put(f"F: {ts_now()} INFO connected {port} @ {baud}")

            while not stop_evt.is_set():
                n = ser.in_waiting
                if n:
                    data = ser.read(n)
                    if data:
                        # cek marker arah
                        events = split_with_dir_markers(data)
                        for lab, payload in events:
                            txt = bytes_to_text(payload, mode)
                            # Format sesuai request: F: <ts> <FRX/FTX> <data>
                            line = f"F: {ts_now()} {lab} {txt}"
                            try:
                                out_q.put(line, timeout=0.2)
                            except queue.Full:
                                pass
                else:
                    time.sleep(0.01)

        except Exception as e:
            out_q.put(f"F: {ts_now()} ERROR {port}: {e}")
            time.sleep(reopen_delay)
        finally:
            if ser:
                try:
                    ser.close()
                except Exception:
                    pass


def serial_reader_rs485(port, baud, bytesize, parity, stopbits, mode,
                        out_q, stop_evt, reopen_delay=1.0, timeout=0.1):
    """
    RS485 tap reader.
    Dengan 1 input, biasanya juga tidak bisa bedain arah,
    jadi output: P: <ts> <data>
    """
    while not stop_evt.is_set():
        ser = None
        try:
            ser = serial.Serial(port=port, baudrate=baud, bytesize=bytesize,
                                parity=parity, stopbits=stopbits, timeout=timeout)
            try:
                ser.reset_input_buffer()
            except Exception:
                pass

            out_q.put(f"P: {ts_now()} INFO connected {port} @ {baud}")

            while not stop_evt.is_set():
                n = ser.in_waiting
                if n:
                    data = ser.read(n)
                    if data:
                        line = f"P: {ts_now()} {bytes_to_text(data, mode)}"
                        try:
                            out_q.put(line, timeout=0.2)
                        except queue.Full:
                            pass
                else:
                    time.sleep(0.01)

        except Exception as e:
            out_q.put(f"P: {ts_now()} ERROR {port}: {e}")
            time.sleep(reopen_delay)
        finally:
            if ser:
                try:
                    ser.close()
                except Exception:
                    pass


def writer(outfile, out_q, stop_evt, also_print=True):
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


def main():
    ap = argparse.ArgumentParser(description="Easy 2-port tap logger (FCC RS232 + RS485) with ms timestamp + auto reconnect")
    ap.add_argument("--fport", required=True)
    ap.add_argument("--pport", required=True)
    ap.add_argument("--baud-f", type=int, default=57600)
    ap.add_argument("--baud-p", type=int, default=19200)
    ap.add_argument("--bytesize", type=int, default=8, choices=[5, 6, 7, 8])
    ap.add_argument("--parity", default="N", choices=["N", "E", "O", "M", "S"])
    ap.add_argument("--stopbits", type=int, default=1, choices=[1, 2])
    ap.add_argument("--mode", default="hex", choices=["hex", "ascii"])
    ap.add_argument("--out", default="log_tap.txt")
    ap.add_argument("--queue-max", type=int, default=10000)
    args = ap.parse_args()

    parity_map = {
        "N": serial.PARITY_NONE,
        "E": serial.PARITY_EVEN,
        "O": serial.PARITY_ODD,
        "M": serial.PARITY_MARK,
        "S": serial.PARITY_SPACE,
    }
    bytesize_map = {5: serial.FIVEBITS, 6: serial.SIXBITS, 7: serial.SEVENBITS, 8: serial.EIGHTBITS}
    stopbits_map = {1: serial.STOPBITS_ONE, 2: serial.STOPBITS_TWO}

    out_q = queue.Queue(maxsize=args.queue_max)
    stop_evt = threading.Event()

    tw = threading.Thread(target=writer, args=(args.out, out_q, stop_evt, True), daemon=True)
    tf = threading.Thread(
        target=serial_reader_fcc,
        args=(args.fport, args.baud_f, bytesize_map[args.bytesize], parity_map[args.parity],
              stopbits_map[args.stopbits], args.mode, out_q, stop_evt),
        daemon=True
    )
    tp = threading.Thread(
        target=serial_reader_rs485,
        args=(args.pport, args.baud_p, bytesize_map[args.bytesize], parity_map[args.parity],
              stopbits_map[args.stopbits], args.mode, out_q, stop_evt),
        daemon=True
    )

    tw.start()
    tf.start()
    tp.start()

    print(f"Logging => {args.out}")
    print("Ctrl+C untuk stop.\n")

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