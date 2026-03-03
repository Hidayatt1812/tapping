#!/usr/bin/env python3
"""
analyze.py - Protocol Pattern Analyzer untuk Serial Port Tapper

Menganalisis log dari tap.py untuk mempelajari protokol serial secara otomatis.
Dirancang untuk fuel pump dispenser (Sanki, Wayne, Gilbarco, dll) tapi
bisa dipakai untuk protokol apapun.

5 Layer analisis:
  L1. Timing     → TX/RX detection dari gap waktu antar packet
  L2. Frame      → cari preamble, start byte, end byte
  L3. Commands   → cluster jenis packet berdasarkan prefix N-gram
  L4. Data       → temukan field BCD (volume, amount, price per unit)
  L5. Checksum   → verifikasi algoritma checksum (XOR, LRC, CRC-16)

Usage:
  python3 analyze.py tapping.txt
  python3 analyze.py tapping.txt -o protocol_map.json
  python3 analyze.py --hex "FC FC FC 02 01 00 27 10 72 99 E2 E3"
"""

import json
import re
import sys
import os
import math
import argparse
from datetime import datetime
from collections import Counter, defaultdict

# Optional: sklearn untuk clustering lebih baik (tidak wajib)
try:
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler
    import numpy as np
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

# ── WARNA TERMINAL ─────────────────────────────────────────────────────────────

C = {
    'reset':   '\033[0m',  'bold':    '\033[1m',
    'red':     '\033[91m', 'green':   '\033[92m',
    'yellow':  '\033[93m', 'blue':    '\033[94m',
    'cyan':    '\033[96m', 'magenta': '\033[95m',
}

def color(name, text):
    return f"{C[name]}{text}{C['reset']}"

def header(title):
    print(f"\n{color('bold', '─'*68)}")
    print(color('cyan', f"  {title}"))
    print(color('bold', '─'*68))


# ── LAYER 0: LOG PARSER ────────────────────────────────────────────────────────

class LogParser:
    """
    Parse log file dari tap.py.
    Format baris: "{label} | {TX|RX} : {YYYY-MM-DD HH:MM:SS.mmm} {hex bytes}"
    """
    LINE_RE = re.compile(
        r'^(.+?)\s*\|\s*(TX|RX)\s*:\s*'
        r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)\s+'
        r'([0-9A-Fa-f][0-9A-Fa-f ]+)$'
    )

    def parse_file(self, filepath):
        packets = []
        prev_time = None

        with open(filepath, 'r', errors='replace') as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                m = self.LINE_RE.match(line)
                if not m:
                    continue

                label, direction, ts_str, hex_str = m.groups()

                try:
                    ts = datetime.strptime(ts_str.strip(), '%Y-%m-%d %H:%M:%S.%f')
                except ValueError:
                    continue

                try:
                    raw = bytes.fromhex(hex_str.replace(' ', ''))
                except ValueError:
                    continue

                if not raw:
                    continue

                gap_ms = None
                if prev_time is not None:
                    gap_ms = (ts - prev_time).total_seconds() * 1000

                packets.append({
                    'idx':                   len(packets),
                    'lineno':                lineno,
                    'label':                 label.strip(),
                    'direction_heuristic':   direction,
                    'direction':             direction,   # akan diperbarui L1
                    'direction_source':      'heuristic',
                    'timestamp':             ts,
                    'gap_ms':                gap_ms,
                    'raw':                   raw,
                    'length':                len(raw),
                })
                prev_time = ts

        return packets

    def parse_hex_string(self, hex_str, label='MANUAL'):
        """Buat pseudo-packet dari raw hex string untuk analisis manual."""
        try:
            raw = bytes.fromhex(hex_str.replace(' ', ''))
        except ValueError:
            return []

        if not raw:
            return []

        return [{
            'idx':                 0,
            'lineno':              1,
            'label':               label,
            'direction_heuristic': 'RX',
            'direction':           'RX',
            'direction_source':    'manual',
            'timestamp':           datetime.now(),
            'gap_ms':              None,
            'raw':                 raw,
            'length':              len(raw),
        }]


# ── LAYER 1: TIMING ANALYSIS ───────────────────────────────────────────────────

class TimingAnalyzer:
    """
    Deteksi TX/RX dari gap waktu antar packet.

    Prinsip:
      - Master (POS) selalu initiator → gap PANJANG sebelum TX (polling rutin)
      - Slave (Pump) selalu responder → gap PENDEK sebelum RX (response cepat)
    """

    def analyze(self, packets):
        gaps = [p['gap_ms'] for p in packets if p['gap_ms'] is not None]

        if len(gaps) < 3:
            return {
                'status': 'insufficient_data',
                'note':   f'Hanya {len(gaps)} gap tersedia, butuh minimal 3',
                'threshold_ms':      None,
                'confident_count':   0,
                'confident_ratio':   0.0,
            }

        # Bimodal split: gaps pendek (RX) vs gaps panjang (TX)
        sorted_gaps = sorted(gaps)
        mid = len(sorted_gaps) // 2
        low_mean  = sum(sorted_gaps[:mid]) / max(len(sorted_gaps[:mid]), 1)
        high_mean = sum(sorted_gaps[mid:]) / max(len(sorted_gaps[mid:]), 1)
        threshold = max((low_mean + high_mean) / 2, 50.0)

        confident = 0
        for p in packets:
            if p['gap_ms'] is None:
                continue
            if p['gap_ms'] > threshold * 1.5:
                p['direction']        = 'TX'
                p['direction_source'] = 'timing'
                confident += 1
            elif p['gap_ms'] < threshold * 0.5:
                p['direction']        = 'RX'
                p['direction_source'] = 'timing'
                confident += 1

        return {
            'status':            'ok',
            'threshold_ms':      round(threshold, 1),
            'avg_gap_ms':        round(sum(gaps) / len(gaps), 1),
            'low_gap_mean_ms':   round(low_mean, 1),
            'high_gap_mean_ms':  round(high_mean, 1),
            'confident_count':   confident,
            'confident_ratio':   round(confident / len(packets), 2),
        }


# ── LAYER 2: FRAME DETECTOR ────────────────────────────────────────────────────

class FrameDetector:
    """
    Cari struktur frame: preamble sync bytes, start byte (STX/ENQ),
    end byte (ETX), dan posisi length byte.
    """

    KNOWN_START = {
        0x02: 'STX', 0x05: 'ENQ', 0x01: 'SOH',
        0x7E: 'HDLC_FLAG', 0x68: 'IEC_START',
    }
    KNOWN_END = {
        0x03: 'ETX', 0x04: 'EOT', 0x0D: 'CR',
        0x0A: 'LF',  0x16: 'SYN',
    }
    SYNC_CANDIDATES = {0xFC, 0xFF, 0xAA, 0x55, 0xFE, 0x7E, 0xEB, 0x90}

    def analyze(self, packets):
        raws = [p['raw'] for p in packets]

        preamble   = self._detect_preamble(raws)
        pre_len    = preamble['length']
        start_byte = self._detect_start_byte(raws, pre_len)
        end_byte   = self._detect_end_byte(raws)
        length_byte = self._detect_length_byte(raws, pre_len)
        confidence = self._calc_confidence(preamble, start_byte, end_byte)

        return {
            'preamble':    preamble,
            'start_byte':  start_byte,
            'end_byte':    end_byte,
            'length_byte': length_byte,
            'confidence':  confidence,
        }

    def _detect_preamble(self, raws):
        if not raws:
            return {'bytes': [], 'hex': '', 'length': 0, 'confidence': 0.0}

        first_counter = Counter(r[0] for r in raws if r)
        top_byte, top_count = first_counter.most_common(1)[0]
        consistency = top_count / len(raws)

        if consistency < 0.75:
            return {'bytes': [], 'hex': '', 'length': 0, 'confidence': 0.0}

        # Cek berapa byte berturut-turut yang sama (repeated sync pattern)
        preamble_bytes = []
        max_check = min(6, min(len(r) for r in raws if r))
        for pos in range(max_check):
            cnt = Counter(r[pos] for r in raws if len(r) > pos)
            byte, ratio_count = cnt.most_common(1)[0]
            ratio = ratio_count / len(raws)
            if ratio >= 0.75 and (byte == top_byte or byte in self.SYNC_CANDIDATES):
                preamble_bytes.append(byte)
            else:
                break

        # Anggap preamble kalau >= 2 byte berulang, atau 1 byte known sync
        if len(preamble_bytes) >= 2:
            return {
                'bytes':      [f'{b:02X}' for b in preamble_bytes],
                'hex':        ' '.join(f'{b:02X}' for b in preamble_bytes),
                'length':     len(preamble_bytes),
                'confidence': round(consistency, 2),
            }
        elif len(preamble_bytes) == 1 and top_byte in self.SYNC_CANDIDATES:
            return {
                'bytes':      [f'{top_byte:02X}'],
                'hex':        f'{top_byte:02X}',
                'length':     1,
                'confidence': round(consistency * 0.7, 2),
            }

        return {'bytes': [], 'hex': '', 'length': 0, 'confidence': 0.0}

    def _detect_start_byte(self, raws, pre_len):
        if not raws:
            return None
        max_pos = min(pre_len + 3, min(len(r) for r in raws if r))
        for pos in range(pre_len, max_pos):
            cnt = Counter(r[pos] for r in raws if len(r) > pos)
            byte, count = cnt.most_common(1)[0]
            ratio = count / len(raws)
            if ratio >= 0.75 and byte in self.KNOWN_START:
                return {
                    'position':    pos,
                    'byte':        f'{byte:02X}',
                    'meaning':     self.KNOWN_START[byte],
                    'consistency': round(ratio, 2),
                }
        return None

    def _detect_end_byte(self, raws):
        if not raws:
            return None
        for pos_from_end in [-1, -2]:
            cnt = Counter(r[pos_from_end] for r in raws if len(r) >= abs(pos_from_end))
            byte, count = cnt.most_common(1)[0]
            ratio = count / len(raws)
            if ratio >= 0.70 and byte in self.KNOWN_END:
                return {
                    'position_from_end': pos_from_end,
                    'byte':              f'{byte:02X}',
                    'meaning':           self.KNOWN_END[byte],
                    'consistency':       round(ratio, 2),
                }
        return None

    def _detect_length_byte(self, raws, pre_len):
        if len(raws) < 3:
            return None
        min_len = min(len(r) for r in raws)
        for pos in range(pre_len, min(pre_len + 4, min_len)):
            matches = sum(
                1 for r in raws
                if len(r) > pos and (
                    r[pos] == len(r) or
                    r[pos] == len(r) - pre_len or
                    r[pos] == len(r) - pos - 1
                )
            )
            if matches / len(raws) >= 0.70:
                return {'position': pos, 'consistency': round(matches / len(raws), 2)}
        return None

    def _calc_confidence(self, preamble, start_byte, end_byte):
        score = 0.0
        if preamble['length'] > 0:
            score += preamble['confidence'] * 0.35
        if start_byte:
            score += start_byte['consistency'] * 0.40
        if end_byte:
            score += end_byte['consistency'] * 0.25
        return round(score, 2)


# ── LAYER 3: COMMAND CLUSTERER ─────────────────────────────────────────────────

class CommandClusterer:
    """
    Kelompokkan packet berdasarkan N-gram prefix byte untuk menemukan
    jenis-jenis command yang berbeda dalam protokol.
    """

    def analyze(self, packets, preamble_len=0):
        if not packets:
            return {}

        # Strip preamble sebelum analisis
        stripped = []
        for p in packets:
            payload = p['raw'][preamble_len:] if len(p['raw']) > preamble_len else p['raw']
            stripped.append({
                'direction': p['direction'],
                'raw':       payload,
                'length':    len(payload),
                'source':    p,
            })

        return {
            'prefix_1byte':       self._top_prefix(stripped, 1),
            'prefix_2byte':       self._top_prefix(stripped, 2),
            'prefix_3byte':       self._top_prefix(stripped, 3),
            'command_groups':     self._group_commands(stripped),
            'length_distribution': self._length_dist(stripped),
        }

    def _top_prefix(self, stripped, n):
        counter = Counter()
        for s in stripped:
            if len(s['raw']) >= n:
                prefix = ' '.join(f'{b:02X}' for b in s['raw'][:n])
                counter[prefix] += 1
        total = len(stripped)
        return [
            {'prefix': k, 'count': v, 'ratio': round(v / total, 2)}
            for k, v in counter.most_common(8)
        ]

    def _group_commands(self, stripped):
        groups = defaultdict(list)
        for s in stripped:
            if len(s['raw']) >= 2:
                key = ' '.join(f'{b:02X}' for b in s['raw'][:2])
            elif len(s['raw']) == 1:
                key = f'{s["raw"][0]:02X}'
            else:
                key = 'EMPTY'
            groups[key].append(s)

        result = []
        for prefix, members in sorted(groups.items(), key=lambda x: -len(x[1])):
            lengths    = [m['length'] for m in members]
            dir_count  = Counter(m['direction'] for m in members)
            dominant   = dir_count.most_common(1)[0][0]
            dir_conf   = dir_count[dominant] / len(members)

            result.append({
                'command_id':            f'CMD_{prefix.replace(" ", "_")}',
                'prefix':                prefix,
                'count':                 len(members),
                'dominant_direction':    dominant,
                'direction_confidence':  round(dir_conf, 2),
                'length_min':            min(lengths),
                'length_max':            max(lengths),
                'length_avg':            round(sum(lengths) / len(lengths), 1),
                'interpretation':        self._guess_meaning(members, dominant),
            })

        return result

    def _guess_meaning(self, members, direction):
        avg_len = sum(m['length'] for m in members) / len(members)
        if direction == 'TX':
            return 'poll_or_request' if avg_len <= 10 else 'write_command'
        else:
            if avg_len <= 8:   return 'ack_or_status'
            if avg_len <= 20:  return 'data_response'
            return 'transaction_data'

    def _length_dist(self, stripped):
        lengths = [s['length'] for s in stripped]
        if not lengths:
            return {}
        return {
            'min':          min(lengths),
            'max':          max(lengths),
            'avg':          round(sum(lengths) / len(lengths), 1),
            'distribution': dict(Counter(lengths).most_common(10)),
        }


# ── LAYER 4: DATA FIELD DETECTOR ──────────────────────────────────────────────

class DataFieldDetector:
    """
    Temukan field data dalam packet:
    - BCD encoded numbers (volume liter, amount, price per unit)
    - Field statis (header/address - sama di semua packet)
    - Field dinamis (data transaksi - berubah antar packet)
    - Entropy per posisi (tinggi = data, rendah = header)
    """

    def analyze(self, packets, preamble_len=0, start_byte_pos=None):
        if not packets:
            return {}

        # Offset konten: skip preamble + start byte
        content_offset = preamble_len
        if start_byte_pos is not None:
            content_offset = start_byte_pos + 1

        payloads = [p['raw'][content_offset:] for p in packets if len(p['raw']) > content_offset]
        if not payloads:
            payloads = [p['raw'] for p in packets]

        result = {
            'content_offset':        content_offset,
            'bcd_fields':            self._find_bcd_fields(payloads),
            'static_fields':         self._find_static_fields(payloads),
            'variable_fields':       self._find_variable_fields(payloads),
            'entropy_per_position':  self._entropy_per_pos(payloads),
        }
        result['field_interpretations'] = self._interpret_bcd(result['bcd_fields'], payloads)

        return result

    # ── BCD Detection ──────────────────────────────────────────────────────────

    def _is_bcd(self, byte):
        return (byte >> 4) <= 9 and (byte & 0x0F) <= 9

    def _find_bcd_fields(self, payloads):
        if not payloads:
            return []
        min_len = min(len(p) for p in payloads)
        if min_len == 0:
            return []

        fields = []
        in_bcd = False
        start  = 0

        for pos in range(min_len):
            bcd_count = sum(1 for p in payloads if len(p) > pos and self._is_bcd(p[pos]))
            bcd_ratio = bcd_count / len(payloads)

            if bcd_ratio >= 0.80:
                if not in_bcd:
                    in_bcd = True
                    start  = pos
            else:
                if in_bcd and pos - start >= 2:
                    fields.append(self._make_bcd_field(payloads, start, pos))
                in_bcd = False

        if in_bcd and min_len - start >= 2:
            fields.append(self._make_bcd_field(payloads, start, min_len))

        return fields

    def _make_bcd_field(self, payloads, start, end):
        samples = []
        for p in payloads[:6]:
            if len(p) >= end:
                samples.append(' '.join(f'{b:02X}' for b in p[start:end]))
        return {
            'offset':                start,
            'length':                end - start,
            'encoding':              'BCD',
            'sample_hex':            samples,
            'sample_decimal':        [s.replace(' ', '') for s in samples],
        }

    # ── Static / Variable Fields ───────────────────────────────────────────────

    def _find_static_fields(self, payloads):
        """Byte yang nilainya sama di semua packet → kemungkinan header/address."""
        if len(payloads) < 2:
            return []
        min_len = min(len(p) for p in payloads)

        static_positions = []
        for pos in range(min_len):
            values = set(p[pos] for p in payloads if len(p) > pos)
            if len(values) == 1:
                static_positions.append({'offset': pos, 'value': f'{list(values)[0]:02X}'})

        # Group consecutive static bytes
        if not static_positions:
            return []
        groups = []
        group  = [static_positions[0]]
        for i in range(1, len(static_positions)):
            if static_positions[i]['offset'] == static_positions[i-1]['offset'] + 1:
                group.append(static_positions[i])
            else:
                groups.append(group)
                group = [static_positions[i]]
        groups.append(group)

        return [
            {
                'offset': g[0]['offset'],
                'length': len(g),
                'bytes':  ' '.join(x['value'] for x in g),
                'note':   'header_or_address',
            }
            for g in groups
        ]

    def _find_variable_fields(self, payloads):
        """Byte yang berubah antar packet → kemungkinan data transaksi."""
        if len(payloads) < 2:
            return []
        min_len = min(len(p) for p in payloads)

        variable = []
        for pos in range(min_len):
            values = [p[pos] for p in payloads if len(p) > pos]
            unique = len(set(values))
            if unique > 1:
                variable.append({
                    'offset':        pos,
                    'unique_values': unique,
                    'samples':       [f'{v:02X}' for v in sorted(set(values))[:5]],
                    'note':          'transaction_data',
                })
        return variable

    def _entropy_per_pos(self, payloads):
        """Shannon entropy per posisi byte. Tinggi = data dinamis."""
        if not payloads:
            return []
        min_len = min(len(p) for p in payloads)
        result  = []
        for pos in range(min_len):
            values  = [p[pos] for p in payloads if len(p) > pos]
            counter = Counter(values)
            total   = len(values)
            entropy = -sum((c/total) * math.log2(c/total) for c in counter.values() if c > 0)
            result.append(round(entropy, 2))
        return result

    # ── Interpretation ─────────────────────────────────────────────────────────

    def _interpret_bcd(self, bcd_fields, payloads):
        """
        Coba interpretasikan field BCD dalam konteks fuel pump:
        price_per_unit, volume, amount, transaction_counter
        """
        interpretations = []

        for field in bcd_fields:
            offset = field['offset']
            length = field['length']

            # Ambil nilai numerik dari semua packet
            nums = []
            for p in payloads:
                if len(p) >= offset + length:
                    bcd_str = ''.join(f'{b:02X}' for b in p[offset:offset+length])
                    try:
                        nums.append(int(bcd_str))
                    except ValueError:
                        pass

            if not nums:
                continue

            avg_val    = sum(nums) / len(nums)
            min_val    = min(nums)
            max_val    = max(nums)
            is_const   = (min_val == max_val)  # True = sama di semua packet
            candidates = []

            # ── Fuel pump context: range check per field type ──────────────────

            # Price per liter: Rp 5.000–15.000 → encoded 5000–15000
            if 5000 <= avg_val <= 15000:
                candidates.append({
                    'field':      'price_per_unit',
                    'value':      f'Rp {avg_val:,.0f}/Liter',
                    'confidence': 0.85 if is_const else 0.65,
                    'note':       'Tetap antar transaksi' if is_const else 'Berubah - cek',
                })

            # Volume: 0.001 – 999.999 liter (BCD x1000)
            if length >= 3 and 1 <= avg_val <= 999999:
                candidates.append({
                    'field':      'volume_liter',
                    'value':      f'{avg_val/1000:.3f} L',
                    'confidence': 0.70 if not is_const else 0.40,
                    'note':       'Berubah per transaksi' if not is_const else 'Tetap - bukan volume',
                })

            # Amount: Rp 1.000 – Rp 999.999.999
            if length >= 3 and 1000 <= avg_val <= 999999999:
                candidates.append({
                    'field':      'transaction_amount',
                    'value':      f'Rp {avg_val:,.0f}',
                    'confidence': 0.65 if not is_const else 0.30,
                    'note':       'Berubah per transaksi' if not is_const else 'Tetap',
                })

            # Transaction counter: 1–9999
            if avg_val <= 9999 and length <= 2 and not is_const:
                candidates.append({
                    'field':      'transaction_counter',
                    'value':      f'#{int(avg_val):04d}',
                    'confidence': 0.55,
                    'note':       'Increment per transaksi',
                })

            if candidates:
                # Sort by confidence
                candidates.sort(key=lambda x: -x['confidence'])
                interpretations.append({
                    'offset':          offset,
                    'length':          length,
                    'avg_value':       avg_val,
                    'is_constant':     is_const,
                    'best_guess':      candidates[0]['field'],
                    'best_value':      candidates[0]['value'],
                    'all_candidates':  candidates,
                })

        return interpretations


# ── LAYER 5: CHECKSUM VALIDATOR ────────────────────────────────────────────────

class ChecksumValidator:
    """
    Test berbagai algoritma checksum untuk menemukan mana yang dipakai
    protokol ini. Test: XOR, LRC (sum), Two's Complement LRC.
    """

    def analyze(self, packets, preamble_len=0):
        raws = [p['raw'] for p in packets]

        if len(raws) < 3:
            return {
                'status': 'insufficient_data',
                'note':   f'Hanya {len(raws)} packet, butuh minimal 3 untuk validasi',
                'best_match': None,
            }

        results = []

        # Test checksum di posisi -1 dan -2
        for chk_pos in [-1, -2]:
            # Test data range: dari berbagai start offset
            for data_start in range(0, min(preamble_len + 4, 5)):
                xor_r = self._test_xor(raws, data_start, chk_pos)
                if xor_r >= 0.70:
                    results.append({
                        'algorithm':          'XOR',
                        'data_start':         data_start,
                        'checksum_position':  chk_pos,
                        'match_ratio':        round(xor_r, 2),
                    })

                lrc_r = self._test_lrc(raws, data_start, chk_pos)
                if lrc_r >= 0.70:
                    results.append({
                        'algorithm':          'LRC',
                        'data_start':         data_start,
                        'checksum_position':  chk_pos,
                        'match_ratio':        round(lrc_r, 2),
                    })

                lrc2_r = self._test_lrc2(raws, data_start, chk_pos)
                if lrc2_r >= 0.70:
                    results.append({
                        'algorithm':          "LRC_2COMP",
                        'data_start':         data_start,
                        'checksum_position':  chk_pos,
                        'match_ratio':        round(lrc2_r, 2),
                    })

        results.sort(key=lambda x: -x['match_ratio'])

        found = bool(results)
        return {
            'status':     'ok' if found else 'not_found',
            'best_match': results[0] if found else None,
            'candidates': results[:5],
            'note':       (
                f"Ditemukan: {results[0]['algorithm']} "
                f"(match {results[0]['match_ratio']*100:.0f}%)"
                if found else
                'Tidak ditemukan - butuh lebih banyak packet atau range checksum lebih besar'
            ),
        }

    def _payload(self, r, data_start, chk_pos):
        chk_idx = len(r) + chk_pos
        if chk_idx <= data_start or chk_idx >= len(r):
            return None, None
        return r[data_start:chk_idx], r[chk_idx]

    def _test_xor(self, raws, data_start, chk_pos):
        matches = 0
        valid   = 0
        for r in raws:
            payload, chk = self._payload(r, data_start, chk_pos)
            if payload is None:
                continue
            valid += 1
            xor = 0
            for b in payload:
                xor ^= b
            if xor == chk:
                matches += 1
        return matches / valid if valid > 0 else 0

    def _test_lrc(self, raws, data_start, chk_pos):
        matches = 0
        valid   = 0
        for r in raws:
            payload, chk = self._payload(r, data_start, chk_pos)
            if payload is None:
                continue
            valid   += 1
            lrc = sum(payload) & 0xFF
            if lrc == chk:
                matches += 1
        return matches / valid if valid > 0 else 0

    def _test_lrc2(self, raws, data_start, chk_pos):
        """Two's complement LRC: (256 - sum) & 0xFF"""
        matches = 0
        valid   = 0
        for r in raws:
            payload, chk = self._payload(r, data_start, chk_pos)
            if payload is None:
                continue
            valid += 1
            lrc = (256 - (sum(payload) & 0xFF)) & 0xFF
            if lrc == chk:
                matches += 1
        return matches / valid if valid > 0 else 0


# ── PROTOCOL ANALYZER (ORCHESTRATOR) ──────────────────────────────────────────

class ProtocolAnalyzer:
    """Orkestrasi semua layer analisis dan output hasil."""

    def __init__(self, verbose=False):
        self.verbose  = verbose
        self.parser   = LogParser()
        self.l1       = TimingAnalyzer()
        self.l2       = FrameDetector()
        self.l3       = CommandClusterer()
        self.l4       = DataFieldDetector()
        self.l5       = ChecksumValidator()

    def analyze_file(self, filepath):
        print(color('bold', '\n' + '═'*68))
        print(color('cyan',  '  PROTOCOL PATTERN ANALYZER  –  Serial Port Tapper'))
        print(color('bold', '═'*68))
        print(f"\n{color('yellow', '[*]')} Membaca log: {color('bold', filepath)}")

        packets = self.parser.parse_file(filepath)
        if not packets:
            print(color('red', '[!] Tidak ada packet yang dapat di-parse.'))
            print(color('yellow', '    Pastikan log dalam format hex (--log-format hex di tap.py)'))
            return None

        print(f"    → {color('green', str(len(packets)))} packet ditemukan")

        labels = sorted(set(p['label'] for p in packets))
        print(f"    → {len(labels)} port: {', '.join(labels)}")
        if not HAS_SKLEARN:
            print(color('yellow', '    [i] scikit-learn tidak tersedia, pakai mode pure-Python'))

        all_results = {}
        for label in labels:
            label_pkts = [p for p in packets if p['label'] == label]
            result = self._analyze_group(label, label_pkts)
            all_results[label] = result

        return all_results

    def analyze_hex(self, hex_str):
        """Analisis satu raw hex string (mode manual)."""
        print(color('bold', '\n' + '═'*68))
        print(color('cyan',  '  PROTOCOL PATTERN ANALYZER  –  MODE HEX MANUAL'))
        print(color('bold', '═'*68))

        packets = self.parser.parse_hex_string(hex_str)
        if not packets:
            print(color('red', '[!] Hex string tidak valid.'))
            return None

        raw = packets[0]['raw']
        print(f"\n{color('yellow', '[*]')} Packet: {' '.join(f'{b:02X}' for b in raw)}")
        print(f"    Length: {len(raw)} bytes\n")

        return self._analyze_group('MANUAL', packets)

    def _analyze_group(self, label, packets):
        header(f"PORT: {label}  ({len(packets)} packets)")

        result = {
            'label':         label,
            'total_packets': len(packets),
            'analysis_time': datetime.now().isoformat(),
        }

        # ── L1: Timing ────────────────────────────────────────────────────────
        print(f"\n{color('yellow', '[L1]')} Timing Analysis")
        l1 = self.l1.analyze(packets)
        result['layer1_timing'] = l1

        if l1['status'] == 'ok':
            print(f"     Threshold TX/RX : {l1['threshold_ms']} ms")
            print(f"     Gap TX rata-rata : {l1['high_gap_mean_ms']} ms")
            print(f"     Gap RX rata-rata : {l1['low_gap_mean_ms']} ms")
            ratio_str = f"{l1['confident_ratio']*100:.0f}%"
            print(f"     Deteksi confident: {l1['confident_count']}/{len(packets)} ({ratio_str})")
        else:
            print(f"     {color('yellow', l1.get('note', 'Tidak cukup data'))}")

        # ── L2: Frame ─────────────────────────────────────────────────────────
        print(f"\n{color('yellow', '[L2]')} Frame Detection")
        l2 = self.l2.analyze(packets)
        result['layer2_frame'] = l2

        pre     = l2['preamble']
        pre_len = pre['length']
        if pre_len > 0:
            print(f"     Preamble  : {color('green', pre['hex'])}  (confidence {pre['confidence']})")
        else:
            print(f"     Preamble  : tidak ditemukan")

        if l2['start_byte']:
            sb = l2['start_byte']
            print(f"     Start byte: 0x{sb['byte']} ({sb['meaning']}) @ pos {sb['position']}  (consistency {sb['consistency']})")
        else:
            print(f"     Start byte: tidak ditemukan")

        if l2['end_byte']:
            eb = l2['end_byte']
            print(f"     End byte  : 0x{eb['byte']} ({eb['meaning']}) @ pos {eb['position_from_end']}  (consistency {eb['consistency']})")
        else:
            print(f"     End byte  : tidak ditemukan")

        if l2['length_byte']:
            lb = l2['length_byte']
            print(f"     Length byte@ pos {lb['position']}  (consistency {lb['consistency']})")

        conf_color = 'green' if l2['confidence'] >= 0.6 else ('yellow' if l2['confidence'] >= 0.3 else 'red')
        print(f"     Frame conf : {color(conf_color, str(l2['confidence']))}")

        # ── L3: Commands ──────────────────────────────────────────────────────
        print(f"\n{color('yellow', '[L3]')} Command Clustering")
        l3 = self.l3.analyze(packets, pre_len)
        result['layer3_commands'] = l3

        groups = l3.get('command_groups', [])
        len_dist = l3.get('length_distribution', {})
        print(f"     {len(groups)} tipe command, panjang {len_dist.get('min','?')}–{len_dist.get('max','?')} byte (avg {len_dist.get('avg','?')})")

        for g in groups[:8]:
            dir_tag = color('red', '→TX') if g['dominant_direction'] == 'TX' else color('blue', '←RX')
            print(f"     [{dir_tag}] {g['command_id']:<28} "
                  f"n={g['count']:<4} "
                  f"len={g['length_avg']:<5} "
                  f"→ {g['interpretation']}")

        # ── L4: Data Fields ───────────────────────────────────────────────────
        print(f"\n{color('yellow', '[L4]')} Data Field Detection (BCD / Fuel Pump)")

        # Prioritaskan packet RX panjang (kemungkinan berisi data transaksi)
        rx_long = [p for p in packets if p['direction'] == 'RX' and p['length'] > 10]
        analyze_pkts = rx_long if rx_long else packets

        start_pos = l2['start_byte']['position'] if l2['start_byte'] else None
        l4 = self.l4.analyze(analyze_pkts, pre_len, start_pos)
        result['layer4_data_fields'] = l4

        bcd_fields = l4.get('bcd_fields', [])
        print(f"     Menganalisis {len(analyze_pkts)} packet (RX panjang)")
        print(f"     {len(bcd_fields)} BCD sequence ditemukan:")

        for f_info in bcd_fields:
            samples = ' | '.join(f_info['sample_hex'][:3])
            print(f"     BCD @ offset {f_info['offset']:2d}, len {f_info['length']}B : [{samples}]")

        interps = l4.get('field_interpretations', [])
        if interps:
            print(f"\n     {color('green', 'Interpretasi field (konteks fuel pump):')}")
            for interp in interps:
                const_tag = '(TETAP)' if interp['is_constant'] else '(BERUBAH)'
                best = interp['all_candidates'][0]
                cconf_color = 'green' if best['confidence'] >= 0.70 else 'yellow'
                print(f"     offset {interp['offset']:2d} [{const_tag}]  "
                      f"{color(cconf_color, best['field']):<22} → {best['value']:<20} "
                      f"conf={best['confidence']:.2f}")

        if len(packets) < 5:
            print(color('yellow', f'\n     ⚠ Hanya {len(packets)} packet – static/variable field belum bisa dibedakan'))
            print(color('yellow',  '       Butuh minimal 5 transaksi berbeda untuk bedakan data vs header'))

        # ── L5: Checksum ──────────────────────────────────────────────────────
        print(f"\n{color('yellow', '[L5]')} Checksum Validation")
        l5 = self.l5.analyze(packets, pre_len)
        result['layer5_checksum'] = l5

        if l5['status'] == 'ok' and l5['best_match']:
            bm = l5['best_match']
            print(f"     {color('green', 'DITEMUKAN!')} Algoritma: {color('bold', bm['algorithm'])}")
            print(f"     Data range : byte[{bm['data_start']} : pos{bm['checksum_position']}]")
            print(f"     Match ratio: {bm['match_ratio']*100:.0f}%")
        else:
            print(f"     {color('yellow', l5.get('note', 'Tidak ditemukan'))}")

        # ── Summary ───────────────────────────────────────────────────────────
        summary = self._build_summary(result, packets)
        result['summary'] = summary
        self._print_summary(summary, len(packets))

        return result

    def _build_summary(self, result, packets):
        l2    = result.get('layer2_frame', {})
        l1    = result.get('layer1_timing', {})
        l4    = result.get('layer4_data_fields', {})
        l5    = result.get('layer5_checksum', {})
        l3    = result.get('layer3_commands', {})

        chk_algo = None
        if l5.get('best_match'):
            chk_algo = l5['best_match']['algorithm']

        interps = l4.get('field_interpretations', [])
        field_map = {i['best_guess']: i['best_value'] for i in interps}

        return {
            'total_packets':       len(packets),
            'preamble':            l2.get('preamble', {}).get('hex') or 'not found',
            'start_byte':          l2.get('start_byte', {}).get('byte') if l2.get('start_byte') else None,
            'end_byte':            l2.get('end_byte', {}).get('byte') if l2.get('end_byte') else None,
            'checksum_algorithm':  chk_algo,
            'command_types_found': len(l3.get('command_groups', [])),
            'bcd_fields_found':    len(l4.get('bcd_fields', [])),
            'field_map':           field_map,
            'timing_threshold_ms': l1.get('threshold_ms'),
            'needs_more_data':     len(packets) < 20,
        }

    def _print_summary(self, s, n_packets):
        header('SUMMARY')
        print(f"  Total packet dianalisis : {s['total_packets']}")
        print(f"  Preamble                : {s['preamble']}")
        print(f"  Start byte              : {s['start_byte'] or 'tidak ditemukan'}")
        print(f"  End byte                : {s['end_byte'] or 'tidak ditemukan'}")
        print(f"  Checksum algorithm      : {s['checksum_algorithm'] or 'belum ditentukan'}")
        print(f"  Tipe command ditemukan  : {s['command_types_found']}")
        print(f"  BCD field ditemukan     : {s['bcd_fields_found']}")

        if s['field_map']:
            print(f"\n  {color('green', 'Field data teridentifikasi:')}")
            for field_name, field_val in s['field_map'].items():
                print(f"    {field_name:<25} → {field_val}")

        if s['needs_more_data']:
            print(f"\n  {color('yellow', '⚠  Rekomendasi untuk akurasi lebih tinggi:')}")
            tips = [
                f"Packet saat ini: {n_packets} → butuh minimal 20-50 packet",
                "Capture beberapa transaksi lengkap (isi BBM dari awal sampai selesai)",
                "Pastikan capture kedua sisi komunikasi (TX dari POS + RX dari pump)",
                "Simpan log dengan --log-format hex di tap.py",
            ]
            for i, tip in enumerate(tips, 1):
                print(f"    {i}. {tip}")
        print()


# ── MAIN ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Protocol Pattern Analyzer untuk Serial Port Tapper',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh penggunaan:
  # Analisis log file dari tap.py
  python3 analyze.py tapping_20260302_120000.txt

  # Simpan hasil ke JSON (untuk diload tap.py berikutnya)
  python3 analyze.py tapping.txt -o protocol_map.json

  # Analisis satu packet hex secara manual (mode investigasi)
  python3 analyze.py --hex "FC FC FC 02 01 00 00 00 48 00 00 27 10 00 00 00 48 01 37 00 00 00 72 99 02 02 55 E2 E3"

Output JSON berisi peta protokol yang bisa digunakan tap.py untuk
meningkatkan akurasi deteksi TX/RX dan dekode data transaksi.
        """
    )

    parser.add_argument('logfile',  nargs='?', help='Log file dari tap.py (format hex)')
    parser.add_argument('-o', '--output', default='protocol_map.json',
                        help='Output JSON (default: protocol_map.json)')
    parser.add_argument('--hex', dest='hex_str',
                        help='Analisis satu raw hex string (mode manual)')
    parser.add_argument('-v', '--verbose', action='store_true')

    args = parser.parse_args()

    if not args.logfile and not args.hex_str:
        parser.print_help()
        sys.exit(1)

    analyzer = ProtocolAnalyzer(verbose=args.verbose)

    if args.hex_str:
        results = analyzer.analyze_hex(args.hex_str)
        label   = 'MANUAL'
    else:
        if not os.path.exists(args.logfile):
            print(color('red', f'[!] File tidak ditemukan: {args.logfile}'))
            sys.exit(1)
        results = analyzer.analyze_file(args.logfile)
        label   = None

    if results is None:
        sys.exit(1)

    # Serialisasi JSON (handle datetime & bytes)
    def _serial(obj):
        if isinstance(obj, datetime): return obj.isoformat()
        if isinstance(obj, bytes):    return list(obj)
        raise TypeError(f'Type {type(obj)} not serializable')

    with open(args.output, 'w') as f:
        json.dump(results, f, indent=2, default=_serial, ensure_ascii=False)

    print(f"{color('green', '✓')} Protocol map tersimpan: {color('bold', args.output)}")
    print(f"  Gunakan file ini untuk sesi tapping berikutnya.\n")


if __name__ == '__main__':
    main()
