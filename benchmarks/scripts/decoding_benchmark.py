"""
bcif_bench.py
-------------
Minimal binaryCIF reader with benchmarking.

Loops over every *.bcif / *.bcif.gz file found in INPUT_DIR, reads each one
twice (cold – no dict, warm – reusing the decoded dict), and writes timing
results to OUTPUT_CSV.

Usage
-----
    python bcif_bench.py [input_dir] [output_csv]

Defaults
--------
    input_dir  : ./bcif_data
    output_csv : ./bcif_benchmark.csv
"""

import csv
import gzip
import logging
import os
import struct
import sys
import time
from collections import OrderedDict

import msgpack

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Encoding type codes → (type name, struct format, min, max)
# ---------------------------------------------------------------------------
_BCIF_CODE_TYPE = {
    1:  ("integer_8",           "b", -0x80,        0x7F),
    2:  ("integer_16",          "h", -0x8000,       0x7FFF),
    3:  ("integer_32",          "i", -0x80000000,   0x7FFFFFFF),
    4:  ("unsigned_integer_8",  "B", 0,             0xFF),
    5:  ("unsigned_integer_16", "H", 0,             0xFFFF),
    6:  ("unsigned_integer_32", "I", 0,             0xFFFFFFFF),
    32: ("float_32",            "f", 1.175494351e-38,  3.402823466e38),
    33: ("float_64",            "d", 2.225073859e-308, 1.797693135e308),
}
_FMT = {c: v[1] for c, v in _BCIF_CODE_TYPE.items()}


# ---------------------------------------------------------------------------
# Decoder helpers
# ---------------------------------------------------------------------------

def _byte_array(data, enc):
    fmt = _FMT[enc["type"]]
    n   = len(data) // struct.calcsize(fmt)
    return struct.unpack("<" + fmt * n, data)


def _integer_packing(data, enc):
    unsigned   = enc["isUnsigned"]
    byte_count = enc["byteCount"]
    if unsigned:
        limit = 0xFF if byte_count == 1 else 0xFFFF
        result, value, i = [], 0, 0
        while i < len(data):
            v = data[i]
            while v == limit:
                value += v
                i += 1
                v = data[i]
            result.append(value + v)
            value = 0
            i += 1
    else:
        upper = 0x7F  if byte_count == 1 else 0x7FFF
        lower = -0x80 if byte_count == 1 else -0x8000
        result, value, i = [], 0, 0
        while i < len(data):
            v = data[i]
            while v == upper or v == lower:
                value += v
                i += 1
                v = data[i]
            result.append(value + v)
            value = 0
            i += 1
    return result


def _delta(data, enc):
    val = enc["origin"]
    out = []
    for d in data:
        val += d
        out.append(val)
    return out


def _run_length(data, _enc):
    data = list(data)
    out  = []
    for i in range(0, len(data), 2):
        out.extend([data[i]] * data[i + 1])
    return out


def _fixed_point(data, enc):
    factor = float(enc["factor"])
    return [float(v) / factor for v in data]


def _interval_quantization(data, enc):
    delta  = float(enc["max"] - enc["min"]) / float(enc["numSteps"] - 1)
    minval = enc["min"]
    return [minval + delta * v for v in data]


def _string_array(data, enc):
    offsets = list(decode(enc["offsets"], enc["offsetEncoding"]))
    indices = decode(data, enc["dataEncoding"])
    raw     = enc["stringData"]
    uniq    = [raw[offsets[i]:offsets[i + 1]] for i in range(len(offsets) - 1)]
    return [uniq[i] if i >= 0 else None for i in indices]


_DECODERS = {
    "ByteArray":            _byte_array,
    "IntegerPacking":       _integer_packing,
    "Delta":                _delta,
    "RunLength":            _run_length,
    "FixedPoint":           _fixed_point,
    "IntervalQuantization": _interval_quantization,
    "StringArray":          _string_array,
}


def decode(data, encoding_list):
    """Apply the encoding pipeline in reverse (innermost first)."""
    for enc in reversed(encoding_list):
        data = _DECODERS[enc["kind"]](data, enc)
    return data


# ---------------------------------------------------------------------------
# Core reader
# ---------------------------------------------------------------------------

def read_bcif(path: str) -> list:
    """
    Read a binaryCIF file (plain or .gz) and return a list of dicts:
        [{ "header": str, "categories": { cat_name: { attr_name: [values] } } }]
    """
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rb") as fh:
        raw = msgpack.unpack(fh, raw=False)
    return _decode_blocks(raw)


def _decode_blocks(raw: dict) -> list:
    """Decode all blocks from an already-unpacked msgpack dict."""
    blocks = []
    for block in raw.get("dataBlocks", []):
        header     = block.get("header", "")
        categories = OrderedDict()
        for cat in block.get("categories", []):
            cat_name = cat["name"].lstrip("_")
            columns  = OrderedDict()
            for col in cat.get("columns", []):
                attr_name  = col["name"]
                values     = decode(col["data"]["data"], col["data"]["encoding"])
                mask_block = col.get("mask")
                if mask_block:
                    mask   = decode(mask_block["data"], mask_block["encoding"])
                    values = [
                        "?" if m == 2 else "." if m == 1 else v
                        for v, m in zip(values, mask)
                    ]
                columns[attr_name] = list(values)
            categories[cat_name] = columns
        blocks.append({"header": header, "categories": categories})
    return blocks


# ---------------------------------------------------------------------------
# Benchmark helpers
# ---------------------------------------------------------------------------

def _summarise(blocks: list) -> dict:
    """Return lightweight summary stats."""
    total_rows = 0
    total_cats = 0
    for b in blocks:
        total_cats += len(b["categories"])
        for cols in b["categories"].values():
            lens = [len(v) for v in cols.values()]
            total_rows += max(lens) if lens else 0
    return {"blocks": len(blocks), "categories": total_cats, "rows": total_rows}


def benchmark_file(path: str) -> dict:
    """
    Time two modes for *path* (single run each):

    1. cold – full pipeline: open file → msgpack unpack → decode.
    2. warm – msgpack dict pre-loaded; only decode is timed.

    Returns a dict of results.
    """
    filename = os.path.basename(path)

    # ── MODE 1: cold (no dict) ────────────────────────────────────────────
    t0      = time.perf_counter()
    blocks  = read_bcif(path)
    cold_s  = time.perf_counter() - t0
    summary = _summarise(blocks)

    # ── Pre-load raw msgpack dict (the "input dictionary") ────────────────
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rb") as fh:
        raw_dict = msgpack.unpack(fh, raw=False)

    # ── MODE 2: warm (with dict already in memory) ────────────────────────
    t0     = time.perf_counter()
    _decode_blocks(raw_dict)
    warm_s = time.perf_counter() - t0

    return {
        "filename":       filename,
        "file_size_kb":   round(os.path.getsize(path) / 1024, 2),
        "num_blocks":     summary["blocks"],
        "num_categories": summary["categories"],
        "total_rows":     summary["rows"],
        "cold_ms":        round(cold_s * 1000, 3),
        "warm_ms":        round(warm_s * 1000, 3),
        "speedup_x":      round(cold_s / max(warm_s, 1e-9), 2),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    input_dir  = sys.argv[1] if len(sys.argv) > 1 else "./bcif_data"
    output_csv = sys.argv[2] if len(sys.argv) > 2 else "./bcif_benchmark.csv"

    if not os.path.isdir(input_dir):
        print(f"[ERROR] Input directory not found: {input_dir}")
        sys.exit(1)

    bcif_files = sorted(
        os.path.join(input_dir, f)
        for f in os.listdir(input_dir)
        if f.endswith(".bcif") or f.endswith(".bcif.gz")
    )

    if not bcif_files:
        print(f"[WARN] No .bcif or .bcif.gz files found in: {input_dir}")
        sys.exit(0)

    print(f"Found {len(bcif_files)} file(s) in '{input_dir}'.\n")

    rows = []
    for path in bcif_files:
        print(f"  Benchmarking: {os.path.basename(path)} … ", end="", flush=True)
        try:
            result = benchmark_file(path)
            rows.append(result)
            print(f"cold={result['cold_ms']:.3f}ms  warm={result['warm_ms']:.3f}ms  speedup={result['speedup_x']}x")
        except Exception as e:
            print(f"FAILED ({e})")
            logger.exception("Error processing %s", path)

    if not rows:
        print("No results to write.")
        sys.exit(1)

    fieldnames = list(rows[0].keys())
    os.makedirs(os.path.dirname(os.path.abspath(output_csv)), exist_ok=True)
    with open(output_csv, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nResults written to: {output_csv}")


if __name__ == "__main__":
    main()