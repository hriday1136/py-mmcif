from mmcif.io.IoAdapterPy import IoAdapterPy as IoAdapter
from mmcif.api.DictionaryApi import DictionaryApi
from pathlib import Path
import time


def main():
    # SET UP THE DICTIONARY API OBJECT
    # Include common PDBx/mmCIF dictionary and CSM extension (ModelCIF) dictionary
    directory = Path("benchmarks/data/cif")
    sizeList = []
    cifList = ["4HHB",
                "11HB",
                "3HQV",
                "3IFX",
                "3J3Q",
                "9A25",
                "9AAO",
                "9A8K",
                "AF_AFA0A017SEY2F1",
                "MA_MABAKCEPC0001"]

    # Flag controlling whether the auto-detection type system is used (default) or the
    # dictionaryApi-driven column typing (legacy path). Set to False to use the dictionary.
    useAutoDetect = False
    print("Using Auto Detection") if useAutoDetect else print("Using Dictionary API")

    dictFilePathL = [
        "https://raw.githubusercontent.com/wwpdb-dictionaries/mmcif_pdbx/master/dist/mmcif_pdbx_v5_next.dic",
        "https://raw.githubusercontent.com/ihmwg/ModelCIF/master/dist/mmcif_ma_ext.dic",
        "https://mmcif.wwpdb.org/dictionaries/ascii/mmcif_ihm_ext.dic",
        "https://mmcif.wwpdb.org/dictionaries/ascii/mmcif_ihm_flr_ext.dic",
    ]
    myIo = IoAdapter(raiseExceptions=True)

    # Only build the (expensive) DictionaryApi instance when it will actually be used, i.e.
    # when useAutoDetect is False. When useAutoDetect is True, the dictionary dependency is
    # dropped entirely and dictionaryApi is kept as None.
    if useAutoDetect:
        dictionaryApi = None
    else:
        dApiContainerList = []
        for dictFilePath in dictFilePathL:
            dApiContainerList += myIo.readFile(inputFilePath=dictFilePath)
        dictionaryApi = DictionaryApi(containerList=dApiContainerList, consolidate=True)

    for cifId in cifList:
        #cifId = cif_file.stem
        print(f"Processing {cifId}...")

        # INPUT PATHS
        workPath = "benchmarks/data/bcif_autoDetect"
        filePath = f"benchmarks/data/cif/{cifId}.cif"
        outFilePath = f"benchmarks/data/bcif_benchmark_local/{cifId}.bcif"

        startTime = time.perf_counter() # this placement allows to caputure the actual read+write time
        # READ THE MMCIF
        cL = readMmcif(filepath=filePath, workPath=workPath)
        # WRITE THE BCIF
        writeBcif(cL, outFilePath=outFilePath, dictionaryApi=dictionaryApi, useAutoDetect=useAutoDetect)
        endTime = time.perf_counter()
        runtime = (endTime - startTime)*1000
        #sizeList.append(f"{runtime:.3f}")

        # Output file size for reference
        size = Path(outFilePath).stat().st_size
        sizeList.append(size)

    for s in sizeList:
        print(s)


def readMmcif(filepath, workPath, **kwargs):
    raiseExceptions = kwargs.get("raiseExceptions", True)
    useCharRefs = kwargs.get("useCharRefs", True)
    enforceAscii = kwargs.get("enforceAscii", True)
    #
    myIo = IoAdapter(raiseExceptions=raiseExceptions, useCharRefs=useCharRefs)
    containerList = myIo.readFile(filepath, enforceAscii=enforceAscii, outDirPath=workPath, fmt="mmcif")  # type: ignore
    return containerList


def writeBcif(containerList, outFilePath, **kwargs):
    raiseExceptions = kwargs.get("raiseExceptions", True)
    applyTypes = kwargs.get("applyTypes", True)
    useFloat64 = kwargs.get("useFloat64", True)
    useStringTypes = kwargs.get("useStringTypes", False)
    copyInputData = kwargs.get("copyInputData", False)

    # Use the automatic data-type detection system by default. Set to False (and pass a real
    # dictionaryApi instance) to fall back to the legacy dictionary-driven column typing.
    useAutoDetect = kwargs.get("useAutoDetect", True)

    # DictionaryApi object - can provide as input args to IoUtil() or MarshalUtil() up front,
    # or to the individual methods IoUtil.serialize() or MarshalUtil.doExport().
    # Note that doing this significantly speeds up performance when trying to serialize a lot of files,
    # as opposed to forcing this method to create a new DictionaryApi instance every call.
    # When useAutoDetect is True, the dictionary dependency is dropped entirely and this is forced to None.
    dictionaryApi = None if useAutoDetect else kwargs.get("dictionaryApi")

    myIo = IoAdapter(raiseExceptions=raiseExceptions)
    ret = myIo.writeFile(
        outFilePath,
        containerList=containerList,
        fmt="bcif",
        applyTypes=applyTypes,
        dictionaryApi=dictionaryApi,
        useAutoDetect=useAutoDetect,
        useFloat64=useFloat64,
        useStringTypes=useStringTypes,
        copyInputData=copyInputData
    )
    return ret


if __name__ == "__main__":
    main()