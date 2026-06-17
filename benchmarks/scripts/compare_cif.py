# Compare two CIF data containers
'''
### OPTION 1: 
from rcsb.utils.io.MarshalUtil import MarshalUtil
mU=MarshalUtil()

#containerList1=mU.doImport('benchmarks/data/cif/MA_MAASFVASFVG001.cif',fmt='mmcif')
#containerList2=mU.doImport('mmcif/tests/test-output/MA_MAASFVASFVG001-converted.cif',fmt='mmcif')

containerList1=mU.doImport('benchmarks/data/cif/4HHB.cif',fmt='mmcif')
containerList2=mU.doImport('benchmarks/data/bcif_plain/4HHB-with_autoDetect.bcif',fmt='bcif')

c1 = containerList1[0]
c2 = containerList2[0]


for cat in c1.getObjNameList():
    for attr in c1.getObj(cat).getAttributeList():
        c1AttrL = c1.getObj(cat).getAttributeValueList(attr)
        c2AttrL = c2.getObj(cat).getAttributeValueList(attr)
        c1AttrTypedL = []
        c2AttrTypedL = []
        if len(c2AttrL) > 0:
            for i, _ in enumerate(c2AttrL):
                if isinstance(c2AttrL[i], float):
                    c1AttrTypedL.append(float(c1AttrL[i]))
                    c2AttrTypedL.append(float(c2AttrL[i]))
                elif isinstance(c2AttrL[i], int):
                    c1AttrTypedL.append(int(c1AttrL[i]))
                    c2AttrTypedL.append(int(c2AttrL[i]))
                else:
                    c1AttrTypedL.append(str(c1AttrL[i]).replace(".", "?"))  # These may be swapped between mmCIF and BCIF
                    c2AttrTypedL.append(str(c2AttrL[i]).replace(".", "?"))
        matchOk = c1AttrTypedL == c2AttrTypedL
        if not matchOk:
            with open("compare_cif_mismatch.txt", "a") as f:
                 f.write(f"Category and attribute translation mismatch {cat} {attr}: {c1AttrTypedL} (c1) vs. {c2AttrTypedL} (c2)\n")
            


### OR - more concise non-typing version:
from rcsb.utils.io.MarshalUtil import MarshalUtil
mU=MarshalUtil()

containerList1=mU.doImport('benchmarks/data/cif/MA_MAASFVASFVG001.cif',fmt='mmcif')
containerList2=mU.doImport('mmcif/tests/test-output/MA_MAASFVASFVG001-converted.cif',fmt='mmcif')

c1 = containerList1[0]
c2 = containerList2[0]

for cat in c1.getObjNameList():
    for attr in c1.getObj(cat).getAttributeList():
        c1AttrL = c1.getObj(cat).getAttributeValueList(attr)
        c2AttrL = c2.getObj(cat).getAttributeValueList(attr)
        matchOk = c1AttrL == c2AttrL
        if not matchOk:
            print(f"Category and attribute translation mismatch {cat} {attr}: {c1AttrL} (c1) vs. {c2AttrL} (c2)")

'''


import os
import glob
from rcsb.utils.io.MarshalUtil import MarshalUtil

mU = MarshalUtil()

ORIG_DIR = 'benchmarks/data/cif'
NEW_DIR  = 'mmcif/tests/test-output'
MISMATCH_FILE = "compare_cif_mismatch.txt"

# --- Only these IDs will be compared ---
TARGET_IDS = {'1RMN'}  # <-- put your IDs here

open(MISMATCH_FILE, "w").close()

def fmtFromExt(path):
    return 'bcif' if path.lower().endswith('.bcif') else 'mmcif'

def fileKey(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    return stem.split('-')[0]

def typedEqual(v1, v2):
    try:
        if isinstance(v2, float):
            return float(v1) == float(v2)
        elif isinstance(v2, int):
            return int(v1) == int(v2)
        else:
            # Try numeric comparison first — catches "0.250" vs "0.25", "-1.0" vs "-1", etc.
            
            try:
                return float(v1) == float(v2)
            except (ValueError, TypeError):
                pass
            # Added above part until numeric comparison, to account for precision differences
            
            # Fall back to string comparison for true strings
            return str(v1).replace(".", "?") == str(v2).replace(".", "?")
    except (ValueError, TypeError):
        return False

def compareContainers(c1, c2, name1, name2):
    matched = 0
    total = 0
    for cat in c1.getObjNameList():
        obj1 = c1.getObj(cat)
        obj2 = c2.getObj(cat)
        for attr in obj1.getAttributeList():
            c1AttrL = obj1.getAttributeValueList(attr)
            if obj2 is not None and obj2.hasAttribute(attr):
                c2AttrL = obj2.getAttributeValueList(attr)
            else:
                c2AttrL = []
            n = max(len(c1AttrL), len(c2AttrL))
            total += n
            for i in range(n):
                if i < len(c1AttrL) and i < len(c2AttrL) and typedEqual(c1AttrL[i], c2AttrL[i]):
                    matched += 1
                else:
                    v1 = c1AttrL[i] if i < len(c1AttrL) else "<missing>"
                    v2 = c2AttrL[i] if i < len(c2AttrL) else "<missing>"
                    with open(MISMATCH_FILE, "a") as f:
                        f.write(
                            f"[{name1} vs {name2}] mismatch {cat} {attr} [{i}]: "
                            f"{v1!r} (c1) vs. {v2!r} (c2)\n"
                        )
    return matched, total


origFiles = sorted(glob.glob(os.path.join(ORIG_DIR, '*.cif')))
newFilesAll = [p for p in glob.glob(os.path.join(NEW_DIR, '*'))
               if p.lower().endswith(('.cif', '.bcif'))]

newFiles = {}
for path in newFilesAll:
    newFiles[fileKey(path)] = path

for origPath in origFiles:
    key = fileKey(origPath)
    if key not in TARGET_IDS:       # <-- skip anything not in the target list
        continue

    name1 = os.path.basename(origPath)
    newPath = newFiles.get(key)
    if newPath is None:
        print(f"[skip] no matching new file for {name1}")
        continue
    name2 = os.path.basename(newPath)

    try:
        c1 = mU.doImport(origPath, fmt=fmtFromExt(origPath))[0]
        c2 = mU.doImport(newPath, fmt=fmtFromExt(newPath))[0]
    except Exception as e:
        print(f"[error] {name1} -> {name2}: {e}")
        continue

    matched, total = compareContainers(c1, c2, name1, name2)
    pct = (matched / total * 100) if total else 100.0
    print(f"{name1} -> {name2}: {pct:6.2f}% similar ({matched:,} / {total:,} values match)")