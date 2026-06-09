"""
validate_roundtrip.py
---------------------
Validates a binaryCIF encoding round-trip by comparing the data VALUES
from the original mmCIF file against those decoded from the bcif output.

This is the correct test for encoder correctness — byte comparison of
text CIF files will always fail due to formatting differences introduced
by the python-mmcif reader/writer (comment lines, whitespace, float
precision, category ordering).

Usage
-----
    python3 validate_roundtrip.py original.cif output.bcif

What it checks
--------------
  - Same set of categories in both files
  - Same set of attributes per category
  - Same row count per category
  - Same value in every cell (string-normalised for float tolerance)
  - Same sentinel pattern (which cells are '.' or '?')
"""

import sys
import struct
import msgpack


# ---------------------------------------------------------------------------
# Minimal binaryCIF decoder  (no external deps beyond msgpack)
# ---------------------------------------------------------------------------

_BCIF_TYPE = {
    1: ("b", 1),   # Int8
    2: ("h", 2),   # Int16
    3: ("i", 4),   # Int32
    4: ("B", 1),   # Uint8
    5: ("H", 2),   # Uint16
    6: ("I", 4),   # Uint32
    32: ("f", 4),  # Float32
    33: ("d", 8),  # Float64
}


_MISSING = object()  # sentinel for "key truly not present"


def _flex_get(d: dict, key: str):
    """
    Fetch a value from a dict whose keys may be str or bytes.
    Uses an explicit sentinel so falsy values (0, False, [], b"") are
    returned correctly — unlike `d.get(k) or d.get(k.encode())` which
    treats 0 and False as missing.
    """
    v = d.get(key, _MISSING)
    if v is not _MISSING:
        return v
    alt = key.encode() if isinstance(key, str) else key.decode()
    return d.get(alt)   # None if genuinely absent


def _decode_data(data_bytes: bytes, encodings: list) -> list:
    """Apply inverse encodings (last to first) to recover original values."""
    result = data_bytes

    for enc in reversed(encodings):
        kind = _flex_get(enc, "kind")
        if isinstance(kind, bytes):
            kind = kind.decode()

        def g(key, _enc=enc):
            return _flex_get(_enc, key)

        if kind == "ByteArray":
            type_code = g("type")
            fmt_char, itemsize = _BCIF_TYPE[type_code]
            n = len(result) // itemsize
            result = list(struct.unpack_from("<" + fmt_char * n, result))

        elif kind == "Delta":
            origin = g("origin")
            out = []
            acc = origin
            for i, v in enumerate(result):
                if i == 0:
                    acc = origin + v
                else:
                    acc += v
                out.append(acc)
            result = out

        elif kind == "RunLength":
            src_size = g("srcSize")
            out = []
            for i in range(0, len(result), 2):
                out.extend([result[i]] * result[i + 1])
            result = out

        elif kind == "IntegerPacking":
            is_unsigned = g("isUnsigned")
            byte_count  = g("byteCount")
            upper = (0xFF if byte_count == 1 else 0xFFFF) if is_unsigned \
                    else (0x7F if byte_count == 1 else 0x7FFF)
            lower = 0 if is_unsigned else (-upper - 1)
            out = []
            acc = 0
            for v in result:
                if (is_unsigned and v == upper) or (not is_unsigned and (v == upper or v == lower)):
                    acc += v
                else:
                    out.append(acc + v)
                    acc = 0
            result = out

        elif kind == "FixedPoint":
            factor = g("factor")
            result = [v / factor for v in result]

        elif kind == "StringArray":
            string_data     = g("stringData")
            offsets_bytes   = g("offsets")
            offset_encs     = g("offsetEncoding")
            data_encs       = g("dataEncoding")

            if isinstance(string_data, bytes):
                string_data = string_data.decode("utf-8")

            offsets = _decode_data(offsets_bytes, offset_encs)
            indices = _decode_data(result, data_encs)

            strings = [string_data[offsets[i]:offsets[i+1]] for i in range(len(offsets)-1)]
            result  = [strings[idx] if idx >= 0 else None for idx in indices]

    return result


def _k(d, key):
    """Fetch from dict with either str or bytes key."""
    return _flex_get(d, key)


def decode_bcif(path: str) -> dict:
    """
    Decode a binaryCIF file into a nested dict:
      { block_header: { category_name: { attr_name: [values...] } } }
    Also returns mask information as sentinel-substituted values.
    """
    with open(path, "rb") as f:
        raw = msgpack.unpack(f, raw=False)

    result = {}
    for block in _k(raw, "dataBlocks"):
        bheader = _k(block, "header")
        result[bheader] = {}
        for cat in _k(block, "categories"):
            cat_name = _k(cat, "name").lstrip("_")
            row_count = _k(cat, "rowCount")
            result[bheader][cat_name] = {}
            for col in _k(cat, "columns"):
                col_name = _k(col, "name")
                data_obj = _k(col, "data")
                mask_obj = _k(col, "mask")

                values = _decode_data(_k(data_obj, "data"), _k(data_obj, "encoding"))

                # apply mask — replace masked positions with sentinel strings
                if mask_obj is not None:
                    mask = _decode_data(_k(mask_obj, "data"), _k(mask_obj, "encoding"))
                    values = [
                        ("?" if m == 2 else ".") if m else str(v)
                        for v, m in zip(values, mask)
                    ]
                else:
                    values = [str(v) if v is not None else "?" for v in values]

                result[bheader][cat_name][col_name] = values
    return result


# ---------------------------------------------------------------------------
# mmCIF reader  (uses python-mmcif IoAdapterPy)
# ---------------------------------------------------------------------------

def read_cif(path: str) -> dict:
    """Read a text mmCIF file into the same nested dict structure."""
    try:
        from mmcif.io.IoAdapterPy import IoAdapterPy
    except ImportError:
        print("ERROR: python-mmcif not installed. Run: pip install python-mmcif")
        sys.exit(1)

    adapter = IoAdapterPy()
    containers = adapter.readFile(path)
    result = {}
    for container in containers:
        bheader = container.getName()
        result[bheader] = {}
        for cat_name in container.getObjNameList():
            cObj = container.getObj(cat_name)
            result[bheader][cat_name] = {}
            for ii, at_name in enumerate(cObj.getAttributeList()):
                result[bheader][cat_name][at_name] = cObj.getColumn(ii)
    return result


# ---------------------------------------------------------------------------
# Value normalisation — for float tolerance comparison
# ---------------------------------------------------------------------------

def _normalise(v: str) -> str:
    """Normalise a value string for comparison: strip whitespace, unify float repr."""
    v = str(v).strip()
    if v in (".", "?", ""):
        return v
    try:
        f = float(v)
        # Round to 4 dp to absorb FixedPoint precision differences
        return f"{f:.4f}"
    except ValueError:
        return v.lower()


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def compare(cif_path: str, bcif_path: str) -> bool:
    print(f"Reading  CIF : {cif_path}")
    cif_data = read_cif(cif_path)
    print(f"Decoding BCIF: {bcif_path}")
    bcif_data = decode_bcif(bcif_path)

    errors   = 0
    warnings = 0

    cif_blocks  = set(cif_data.keys())
    bcif_blocks = set(bcif_data.keys())

    if cif_blocks != bcif_blocks:
        print(f"\n[FAIL] Block headers differ")
        print(f"  CIF only : {cif_blocks - bcif_blocks}")
        print(f"  BCIF only: {bcif_blocks - cif_blocks}")
        errors += 1
        return False

    for block in sorted(cif_blocks):
        cif_cats  = set(cif_data[block].keys())
        bcif_cats = set(bcif_data[block].keys())

        missing = cif_cats - bcif_cats
        extra   = bcif_cats - cif_cats

        if missing:
            print(f"\n[FAIL] Block '{block}': categories missing from bcif: {missing}")
            errors += 1
        if extra:
            print(f"\n[WARN] Block '{block}': extra categories in bcif: {extra}")
            warnings += 1

        for cat in sorted(cif_cats & bcif_cats):
            cif_attrs  = set(cif_data[block][cat].keys())
            bcif_attrs = set(bcif_data[block][cat].keys())

            missing_attrs = cif_attrs - bcif_attrs
            if missing_attrs:
                print(f"\n[FAIL] {cat}: attributes missing from bcif: {missing_attrs}")
                errors += 1

            for attr in sorted(cif_attrs & bcif_attrs):
                cif_vals  = cif_data[block][cat][attr]
                bcif_vals = bcif_data[block][cat][attr]

                if len(cif_vals) != len(bcif_vals):
                    print(f"\n[FAIL] {cat}.{attr}: row count {len(cif_vals)} vs {len(bcif_vals)}")
                    errors += 1
                    continue

                for row, (cv, bv) in enumerate(zip(cif_vals, bcif_vals)):
                    if _normalise(cv) != _normalise(bv):
                        print(f"\n[FAIL] {cat}.{attr}[{row}]: "
                              f"cif={repr(cv)}  bcif={repr(bv)}")
                        errors += 1
                        if errors > 20:
                            print("\n... too many errors, stopping early.")
                            return False

    print(f"\n{'='*55}")
    if errors == 0 and warnings == 0:
        print("  PASS — all values match.")
    elif errors == 0:
        print(f"  PASS — all values match ({warnings} warning(s)).")
    else:
        print(f"  FAIL — {errors} error(s), {warnings} warning(s).")
    print(f"{'='*55}")

    return errors == 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 validate_roundtrip.py original.cif output.bcif")
        sys.exit(1)
    ok = compare(sys.argv[1], sys.argv[2])
    sys.exit(0 if ok else 1)