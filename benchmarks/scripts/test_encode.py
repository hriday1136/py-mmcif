# test_encode.py
from mmcif.io.IoAdapterPy import IoAdapterPy
from hriday_bcifWriter import BinaryCifWriter

# read the mmCIF file
adapter = IoAdapterPy()
containerList = adapter.readFile("benchmarks/data/cif/4HHB.cif")

# no dictionaryApi argument — auto-detection handles everything
writer = BinaryCifWriter()
ok = writer.serialize("4HHB.bcif", containerList)

print("Success:", ok)