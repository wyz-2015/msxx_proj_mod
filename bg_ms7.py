#!/usr/bin/env python3

import numpy as np
from PIL import Image
import json
import sys
import argparse
from pathlib import Path
# import pprint as pp


class BG():
    Struct_Hinf = np.dtype([  # Hinf、Htbl，7和XX是一致的
        ("layerWidth", np.uint32),  # 本层宽
        ("layerHeight", np.uint32),  # 本层高
        ("blockWidth", np.uint32),  # 块宽
        ("blockHeight", np.uint32),  # 块高
        ("blockCol", np.uint32),  # 网格列数
        ("blockRow", np.uint32),  # 网格行数
    ])

    EMPTY_PIX = np.zeros(4, dtype=np.uint8)

    SCALE = float(np.frombuffer(np.uint32(0x3f4e1d11), dtype=np.float32)[0])
    # 0.805131

    def __init__(self):
        (self.HinfPathList, self.HtblPathList) = ([], [])
        (self.pakJsonPath, self.pakPath) = (Path(), Path())

        self.metadata = dict()
        self.pakMeta = dict()

        self.outDir = Path("./")

    def import_files(self, args: argparse.Namespace):
        self.HinfPathList = args.HinfPathList
        self.HtblPathList = args.HtblPathList

        self.HinfPathList.sort()
        self.HtblPathList.sort()

        self.pakJsonPath = args.pakJsonPath
        self.pakPath = self.pakJsonPath.parent

    def set_outDir(self, outDir: Path):
        if (not outDir.is_dir()):
            raise TypeError("传入类型错误：{0}不是一个目录".format(outDir))

        self.outDir = outDir

    def __get_index_from_path__(self, filePath: Path, suffix: str) -> str:
        """从文件名提取序号名"""
        fileBaseName = filePath.stem
        posIndex = fileBaseName.rfind(suffix) - 1
        index = fileBaseName[posIndex]
        if (index not in "ABC"):
            raise ValueError(
                "从文件名提取序号名错误。本程序对文件名依赖程度较高，请尽量使用指定格式的文件名。\n文件名：{0}，提取所得序号：{1:s}".format(filePath, index))

        return index

    def read_Hinf(self):
        for HinfPath in self.HinfPathList:
            index = self.__get_index_from_path__(HinfPath, "Hinf")

            Hinf = open(HinfPath, "rb")
            HinfData = np.fromfile(Hinf, dtype=self.Struct_Hinf, count=1)[0]
            Hinf.close()

            self.metadata[index] = {k: int(HinfData[k])
                                    for k in self.Struct_Hinf.names}

            # 记录传入文件名，后同
            self.metadata[index]["HinfPath"] = str(HinfPath)

    def read_Htbl(self):
        for HtblPath in self.HtblPathList:
            index = self.__get_index_from_path__(HtblPath, "Htbl")

            Htbl = open(HtblPath, "rb")
            HtblData = np.fromfile(Htbl, dtype=np.int32, count=self.metadata[index]["blockRow"] * self.metadata[index]["blockCol"]).reshape(
                (self.metadata[index]["blockCol"], self.metadata[index]["blockRow"])).T
            # HtblData[x, y]或HtblData[w, h]，与常规的[y, x]不一样
            # 数据格式：(行, 列)
            # [[(0, 0), (1, 0), (2, 0), ...],
            # [(0, 1), (1, 1), (2, 1), ...],
            # ...]
            # 所以最后需要一次转置

            Htbl.close()
            # print(HtblData)

            self.metadata[index]["tbl"] = HtblData.tolist()

            self.metadata[index]["HtblPath"] = str(HtblPath)

    ##########################################
    # 纹理格式
    # https://mgba-emu.github.io/gbatek/#format-5-4x4-texel-compressed-texture/

    def __block2pix__(self, block: np.uint32) -> np.ndarray:
        """
        一个32bit数是一个block。展开为一个4 * 4的texel block
        """
        blockPix = np.zeros(4 * 4, dtype=np.uint8).reshape((4, 4))

        for row in range(4):
            row_num = block >> (row * 8) & 0xff
            for col in range(4):
                pix = row_num >> (col * 2) & 0b11

                blockPix[row, col] = pix

        return blockPix

    def __split_palInfo__(self, index: np.uint16) -> tuple[int, int]:
        """
        解调调色盘信息的16bit数
        """
        palIndex = int(index & 0x3fff)
        mode = int(index >> 14)

        return (palIndex, mode)

    def __bgr555_to_rgba__(self, color: np.uint16) -> np.ndarray:
        """
        原颜色格式为bgr555
        0b[0][bbbbb][ggggg][rrrrr]
        转换为rgba8888
        """
        r = color & 0b11111
        g = color >> 5 & 0b11111
        b = color >> 10 & 0b11111
        a = 0xff

        rgb_double = np.array([r, g, b, 0], dtype=np.float64)
        rgb_double *= (0xff / 0b11111)  # 原本颜色的范围是[0, 0b11111]，映射到[0, 0xff]
        rgb_double[-1] = a

        # 但由于numpy不像纯C下有自动的整数提升机制，现在就编制为8bit，会导致后面计算中出现错误
        # 只能自己先做扩大，后面再压回8bit
        return np.round(rgb_double, 0).astype(np.uint32)

    def __gen_pix__(self, data: int, palInfo: tuple[int, int], pal: np.ndarray) -> np.ndarray:
        """
        按格式规定调制像素
        """
        (palIndex, mode) = palInfo

        # 调制过程中最多可能用到4种颜色，出于偷懒，无论如何就先取出4种颜色

        # (c0, c1) = (self.__bgr555_to_rgba__(
        #    pal[2 * palIndex]), self.__bgr555_to_rgba__(pal[2 * palIndex + 1]))
        # c: color

        # c2 = (self.__bgr555_to_rgba__(pal[2 * palIndex + 2])
        #      if (2 * palIndex + 2 < len(pal)) else EMPTY_PIX)
        # c3 = (self.__bgr555_to_rgba__(pal[2 * palIndex + 3])
        #      if (2 * palIndex + 3 < len(pal)) else EMPTY_PIX)
        (c0, c1) = (pal[2 * palIndex], pal[2 * palIndex + 1])

        # c2、c3不是每种情况都要取的，所以多做一个索引范围判定，用全透明空像素兜底
        c2 = (pal[2 * palIndex + 2]
              if (2 * palIndex + 2 < len(pal)) else self.EMPTY_PIX)
        c3 = (pal[2 * palIndex + 3]
              if (2 * palIndex + 3 < len(pal)) else self.EMPTY_PIX)

        match (data):
            # data的范围是[0b00,0b11]，每种值与对应mode组合对应不同的颜色取法
            case 0:
                return c0.astype(np.uint8)
            case 1:
                return c1.astype(np.uint8)
            case 2:
                match (mode):
                    case 0 | 2:
                        return c2.astype(np.uint8)
                    case 1:
                        return ((c0 + c1) / 2).astype(np.uint8)
                    case 3:
                        return ((5 * c0 + 3 * c1) / 8).astype(np.uint8)
            case 3:
                match (mode):
                    case 0 | 1:
                        return self.EMPTY_PIX
                    case 2:
                        return c3.astype(np.uint8)
                    case 3:
                        return ((3 * c0 + 5 * c1) / 8).astype(np.uint8)

    def __gen_texelBlock__(self, block: np.ndarray, palInfo: tuple[int, int], pal: np.ndarray) -> Image.Image:
        """
        生成4 * 4 texel block，返回一个Image对象
        """
        buffer = np.zeros(4 * 4 * 4, dtype=np.uint8).reshape((4, 4, 4))

        for y in range(4):
            for x in range(4):
                buffer[y, x] = self.__gen_pix__(int(block[y, x]), palInfo, pal)

        return Image.frombuffer("RGBA", (4, 4), buffer)

    def __gen_block__(self, metadata: dict, texIndex: int) -> Image.Image | None:
        """
        pak中一个文件就是一个大block。
        但是pak文件可能是没有实质内容的。
        若能读取实质内容则返回Image对象，否则返回None，到时候画布上不画返回None的
        """
        # 读取pak包中纹理文件，是三种数据直接调制的
        # Htbl数组中的值，除了-2空占位，都是pak包中文件的序号
        rawBlockPath = self.pakPath / \
            self.pakMeta["subFileMetaList"][texIndex]["subFilePath"]
        rawBlock = open(rawBlockPath, "rb")

        # 根据定义，32bit数对应4 * 4px的图像数据，则1px图像数据对应2bit
        # 据此计算一大block占Byte数：W * H * (2 bit / 8 bit)
        dataSize = int(metadata["blockWidth"] *
                       metadata["blockHeight"] * (2 / 8))
        # dataSize / sizeof(uint32)即block数。block数与颜色索引表长度一致
        texelBlockCount = dataSize // 4

        texelBlock_bin = np.fromfile(
            rawBlock, dtype=np.uint32, count=texelBlockCount)
        palInfo_bin = np.fromfile(
            rawBlock, dtype=np.uint16, count=texelBlockCount)
        pal_bgr555 = np.fromfile(rawBlock, dtype=np.uint16)  # 调色盘即后续所有数据

        rawBlock.close()

        if (len(pal_bgr555) == 0):  # 无效的block读不到调色盘数据
            # 全透明块
            # return Image.new("RGBA", (metadata["blockWidth"], metadata["blockHeight"]))
            return None

        texelBlockList = [self.__block2pix__(i) for i in texelBlock_bin]
        palInfoList = [self.__split_palInfo__(i) for i in palInfo_bin]
        palList_rgba8888 = [self.__bgr555_to_rgba__(i) for i in pal_bgr555]

        blockImg = Image.new(
            "RGBA", (metadata["blockWidth"], metadata["blockHeight"]))
        i = 0
        for y in range(0, metadata["blockHeight"], 4):
            for x in range(0, metadata["blockWidth"], 4):
                texelBlock = self.__gen_texelBlock__(
                    texelBlockList[i], palInfoList[i], palList_rgba8888)
                blockImg.paste(texelBlock, (x, y))

                texelBlock.close()
                i += 1

        return blockImg

    def read_tex(self):
        """
        读取texel包，并顺带直接生成图像
        """
        jsonFile = open(self.pakJsonPath, "rt")
        self.pakMeta = json.load(jsonFile)
        jsonFile.close()
        # json中int数不能作键，生成时会被自动转成str，所以现在应转回int
        self.pakMeta["subFileMetaList"] = {int(k): v for (
            k, v) in self.pakMeta["subFileMetaList"].items()}

        # 生成图像

        for (index, metadata) in self.metadata.items():
            if (index not in "ABC"):  # ABC三层才能参与
                continue

            canvas = Image.new(
                "RGBA", (
                    int(metadata["layerWidth"] * self.SCALE),
                    int(metadata["layerHeight"] * self.SCALE)
                ))

            for yb in range(metadata["blockRow"]):
                for xb in range(metadata["blockCol"]):
                    texIndex = metadata["tbl"][yb][xb]

                    if (texIndex == -2):
                        continue

                    blockImg = self.__gen_block__(metadata, texIndex)
                    # print("xb = {0:n}, yb = {1:n}".format(xb, yb))
                    if (blockImg is None):
                        continue

                    canvas.paste(
                        blockImg, (
                            int(xb * metadata["blockWidth"] * self.SCALE),
                            int(yb * metadata["blockHeight"] * self.SCALE)
                        ))
                    # 最匪夷所思的一个问题：缩放
                    # 一block中，设定义大小(W, H)，实质有图像的部分(w, h)
                    # w / W = h / H = SCALE
                    # SCALE是程序中定义的一个常数
                    # 所以画布大小，在画布上贴block的相应步长，只能相应作调整

                    blockImg.close()

            outImgPath = self.outDir / "{0:s}.png".format(index)
            canvas.save(outImgPath)
            canvas.close()

        self.metadata["pakJsonPath"] = str(self.pakJsonPath)

    ##################################################

    def write_json(self):
        jsonFile = open(self.outDir / "bg.json", "wt")
        json.dump(self.metadata, jsonFile, ensure_ascii=False, indent='\t')
        jsonFile.close()

    def read(self):
        self.read_Hinf()
        self.read_Htbl()
        self.read_tex()

        # pp.pprint(self.metadata)
        # print(self.metadata)
        self.write_json()


def main():
    cmdParser = argparse.ArgumentParser(
        description="Metal Slug 7关卡BG提取、<s>重建</s>工具。")
    modeParser = cmdParser.add_subparsers(dest="mode", help="使用模式")

    readParser = modeParser.add_parser("read", help="读取模式")
    readParser.add_argument("--Hinf", action="extend", nargs="+",
                            required=True, help="Hinf文件路径(所有)", dest="HinfPathList", type=Path)
    readParser.add_argument("--Htbl", action="extend", nargs="+",
                            required=True, help="Htbl文件路径(所有)", dest="HtblPathList", type=Path)
    readParser.add_argument("--pak", help="pak包解包结果路径",
                            dest="pakJsonPath", type=Path, required=True)
    readParser.add_argument("-d", "--out-dir", help="导出文件路径",
                            type=Path, required=False, default=Path("./"), dest="outDir")

    writeParser = modeParser.add_parser("write", help="生成模式")

    args = cmdParser.parse_args()
    print(args)

    bg = BG()
    match (args.mode):
        case "read":
            bg.import_files(args)
            bg.set_outDir(args.outDir)
            bg.read()
        case "write":
            raise ValueError("生成模式尚未支持")
        case _:
            raise ValueError("未知模式名：{0:s}".format(args.mode))


if (__name__ == "__main__"):
    sys.exit(main())
