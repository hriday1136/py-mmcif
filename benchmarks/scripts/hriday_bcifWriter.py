#!/usr/bin/env python3
"""
run_bcif_writer.py
------------------
Fetch one or more PDB entries from RCSB and serialize to BinaryCIF (.bcif).

Usage
-----
    python run_bcif_writer.py 5ZMZ --dict mmcif_pdbx_v5_next.dic
    python run_bcif_writer.py 5ZMZ 1ABC 2XYZ --dict mmcif_pdbx_v5_next.dic -o ./output
"""

import argparse
import logging
import os
import sys
import time

logging.disable(logging.CRITICAL)  # silence all mmcif library output

RCSB_BASE_URL = "https://files.rcsb.org/download/"


def _import_mmcif():
    try:
        from mmcif.api.DataCategoryTyped import DataCategoryTyped
        from mmcif.api.DictionaryApi import DictionaryApi
        from mmcif.api.PdbxContainers import DataContainer
        from mmcif.io.BinaryCifWriter import BinaryCifWriter
        from mmcif.io.IoAdapterPy import IoAdapterPy as IoAdapter
        return DataCategoryTyped, DictionaryApi, DataContainer, BinaryCifWriter, IoAdapter
    except ImportError as exc:
        sys.exit(f"[ERROR] Could not import mmcif package: {exc}\nInstall it with: pip install mmcif")


def process_entry(pdb_id, output_dir, d_api, args,
                  DataCategoryTyped, DataContainer, BinaryCifWriter, IoAdapter):
    start = time.time()
    url = RCSB_BASE_URL + pdb_id + ".cif"

    ioPy = IoAdapter()
    container_list = ioPy.readFile(url)
    if not container_list:
        sys.exit(f"[ERROR] No containers found for PDB ID: {pdb_id}")

    # Build typed containers
    typed_list = []
    for container in container_list:
        from mmcif.api.PdbxContainers import DataContainer as DC
        tc = DC(container.getName())
        for cat_name in container.getObjNameList():
            d_obj = container.getObj(cat_name)
            t_obj = DataCategoryTyped(
                d_obj,
                dictionaryApi=d_api,
                copyInputData=True,
                applyMolStarTypes=False,
            )
            tc.append(t_obj)
        typed_list.append(tc)

    # Serialize
    output_path = os.path.join(output_dir, pdb_id + ".bcif")

    bcw = BinaryCifWriter(
        d_api,
        storeStringsAsBytes=args.bytes,
        applyTypes=not args.no_types,
        useStringTypes=args.string_types,
        useFloat64=args.float64,
        copyInputData=False,
        ignoreCastErrors=False,
    )

    ok = bcw.serialize(output_path, typed_list)
    if not ok:
        sys.exit(f"[ERROR] Serialization failed for PDB ID: {pdb_id}")

    elapsed = time.time() - start
    print(f"{pdb_id}: {elapsed:.2f}s")


def main():
    parser = argparse.ArgumentParser(
        description="Fetch PDB entries from RCSB and serialize to BinaryCIF (.bcif)."
    )
    parser.add_argument("inputs", nargs="+", metavar="PDB_ID",
                        help="One or more PDB IDs (e.g. 5ZMZ 1ABC).")
    parser.add_argument("--output-dir", "-o", default=".", metavar="DIR",
                        help="Output directory for .bcif files (default: current directory).")
    parser.add_argument("--dict", "-d", default=None, metavar="DICT_PATH",
                        help="Path to mmCIF/PDBx dictionary (.dic). "
                             "If omitted, looks for mmcif_pdbx_v5_next.dic next to this script.")
    parser.add_argument("--bytes", action="store_true", default=False,
                        help="Store strings as bytes.")
    parser.add_argument("--float64", action="store_true", default=False,
                        help="Use 64-bit float precision.")
    parser.add_argument("--no-types", action="store_true", default=False,
                        help="Skip explicit data type casting.")
    parser.add_argument("--string-types", action="store_true", default=False,
                        help="Treat all data as strings.")
    args = parser.parse_args()

    # Resolve dictionary path
    if args.dict is None:
        candidate = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mmcif_pdbx_v5_next.dic")
        if os.path.isfile(candidate):
            args.dict = candidate
        else:
            sys.exit(
                "[ERROR] No dictionary path supplied and mmcif_pdbx_v5_next.dic not found "
                "next to this script.\nUse --dict /path/to/mmcif_pdbx_v5_next.dic"
            )

    if not os.path.isfile(args.dict):
        sys.exit(f"[ERROR] Dictionary file not found: {args.dict}")

    os.makedirs(args.output_dir, exist_ok=True)

    (DataCategoryTyped, DictionaryApi, DataContainer,
     BinaryCifWriter, IoAdapter) = _import_mmcif()

    # Load dictionary once for all entries
    ioPy = IoAdapter(raiseExceptions=True)
    container_list = ioPy.readFile(inputFilePath=args.dict)
    d_api = DictionaryApi(containerList=container_list, consolidate=True)

    for pdb_id in args.inputs:
        process_entry(pdb_id.upper(), output_dir=args.output_dir, d_api=d_api, args=args,
                      DataCategoryTyped=DataCategoryTyped, DataContainer=DataContainer,
                      BinaryCifWriter=BinaryCifWriter, IoAdapter=IoAdapter)


if __name__ == "__main__":
    main()