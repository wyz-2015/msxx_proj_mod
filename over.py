#!/usr/bin/env python3

import numpy as np
from PIL import Image
import sys
from pathlib import Path


def main(argv: list):
    binPath = Path(argv[1])
    binFile = open(binPath, "rb")

    pal = np.fromfile(binFile, dtype=np.uint8, count=256 * 4).reshape((256, 4))
    # print(pal)
    data = np.fromfile(binFile)

    i = Image.new("P", (512, 512))
    i.putdata(data.tobytes())
    i.putpalette(pal, "RGBA")
    # i.show()

    pngPath = binPath.parent / "{0:s}_unswizzled.png".format(binPath.stem)
    print(pngPath)
    i.save(pngPath)
    i.close()

    binFile.close()


if (__name__ == "__main__"):
    sys.exit(main(sys.argv))
