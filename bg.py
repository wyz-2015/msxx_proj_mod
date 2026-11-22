#!/usr/bin/env python3

import numpy as np
from PIL import Image
import json
import sys
import argparse
from pathlib import Path
from typing import IO, Callable
import pprint as pp

import psp_swizzle


class BG():
    Struct_Hinf = np.dtype([
        ("layerWidth", np.uint32),  # 本层宽
        ("layerHeight", np.uint32),  # 本层高
        ("blockWidth", np.uint32),  # 块宽
        ("blockHeight", np.uint32),  # 块高
        ("blockCol", np.uint32),  # 网格列数
        ("blockRow", np.uint32),  # 网格行数
    ])

    Struct_tex_Head = np.dtype([
        ("entryCount", np.uint32),  # 条目数
        ("animStartIndex", np.int32),  # 动画区间条目下标区间起点，-1代表无动画
        ("animFrameCount", np.uint32),  # 动画帧数，0代表无动画
        ("animFrame_entryCount", np.uint32),  # 每帧占用的连续条目数
        ("animMode", np.uint32),  # 动画模式：0替换式，1叠加式
        ("reversed", np.uint32, (3,))
    ])

    # Struct_Htbl = np.dtype([])
    def __init__(self):
        (self.HinfPathList, self.HtblPathList) = ([], [])
        # (self.HinfList, self.HtblList) = (dict(), dict())
        self.metadata = dict()

        (self.palPath, self.texPath) = (Path(), Path())

        self.outDir = Path("./")

    def import_files(self, args: argparse.Namespace):
        self.HinfPathList = args.HinfPathList
        self.HtblPathList = args.HtblPathList

        self.HinfPathList.sort()
        self.HtblPathList.sort()

        self.palPath = args.palPath
        self.texPath = args.texPath

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

    def read_pal(self):
        palFile = open(self.palPath, "rb")
        # for index in sorted(self.metadata.keys()):
        #    pal_bin = np.fromfile(palFile, dtype=np.uint8,
        #                          count=256 * 4).reshape((256, 4))
        #    self.metadata[index]["palette"] = pal_bin.tolist()
        self.metadata["paletteList"] = []
        while (True):
            pal_bin = np.fromfile(palFile, dtype=np.uint8, count=256 * 4)
            if (len(pal_bin) != 256 * 4):
                break
            self.metadata["paletteList"].append(
                pal_bin.reshape((256, 4)).tolist())
        palFile.close()

        self.metadata["palPath"] = str(self.palPath)

    def __gen_img__(self, metadata: dict, texFile: IO[bytes], texDataOffset: int, filter_func: Callable[[int], bool], frame: int, outName: str):
        canvas = Image.new(
            "RGBA", (metadata["layerWidth"], metadata["layerHeight"]))
        for y in range(metadata["blockRow"]):
            for x in range(metadata["blockCol"]):
                entryIndex = metadata["tbl"][y][x]
                if ((entryIndex == -2) or (not filter_func(entryIndex))):
                    continue

                entry = self.metadata["texture"]["entryList"][entryIndex +
                                                              frame * self.metadata["texture"]["animFrame_entryCount"]]
                if ((type(entry) is int) and entry == -1):
                    continue

                blockImg = Image.new(
                    "P", (metadata["blockWidth"], metadata["blockHeight"]))
                texFile.seek(
                    texDataOffset + entry["blockIndex"] * metadata["blockWidth"] * metadata["blockHeight"], 0)
                imgData = np.fromfile(texFile, dtype=np.uint8, count=metadata["blockWidth"] * metadata["blockHeight"]).reshape(
                    metadata["blockHeight"], metadata["blockWidth"])
                blockImg.putdata(psp_swizzle.unswizzle(
                    metadata["blockHeight"], metadata["blockWidth"], imgData).tobytes())
                blockImg.putpalette(
                    np.array(self.metadata["paletteList"][entry["palIndex"]], dtype=np.uint8).tobytes(), "RGBA")

                canvas.paste(
                    blockImg, (x * metadata["blockWidth"], y * metadata["blockHeight"]))
                blockImg.close()

        canvas.save(self.outDir / "{0:s}.png".format(outName))
        canvas.close()

    def read_tex(self):
        """
        读取tex文件，并顺带直接生成图像
        """
        texFile = open(self.texPath, "rb")
        tex_head_bin = np.fromfile(
            texFile, dtype=self.Struct_tex_Head, count=1)[0]
        self.metadata["texture"] = {
            k: int(tex_head_bin[k]) for k in self.Struct_tex_Head.names if (k != "reversed")}
        self.metadata["texture"]["reversed"] = tex_head_bin["reversed"].tolist()

        entryList_bin = np.fromfile(
            texFile, dtype=np.int32, count=self.metadata["texture"]["entryCount"])
        self.metadata["texture"]["entryList"] = []
        for entry_bin in entryList_bin:
            if (entry_bin == -1):
                self.metadata["texture"]["entryList"].append(-1)
            else:
                palIndex = int(entry_bin >> 24)
                blockIndex = int(entry_bin & 0xffffff)

                self.metadata["texture"]["entryList"].append({
                    "palIndex": palIndex,
                    "blockIndex": blockIndex
                })

        texDataOffset = texFile.tell()

        # 生成图像

        for (index, metadata) in self.metadata.items():
            if (index not in "ABC"):  # ABC三层才能参与
                continue

            # 一些关卡的BG是动态的。这里的设计是静态部分与动态部分分开生成

            # 静态
            self.__gen_img__(metadata, texFile, texDataOffset,
                             lambda x: (self.metadata["texture"]["animStartIndex"] == -1) or (
                                 (self.metadata["texture"]["animStartIndex"] != -1) and (x < self.metadata["texture"]["animStartIndex"])),
                             0, index)

            # 动态
            if (self.metadata["texture"]["animStartIndex"] != -1):
                for f in range(self.metadata["texture"]["animFrameCount"]):
                    self.__gen_img__(metadata, texFile, texDataOffset,
                                     lambda x: x >= self.metadata["texture"]["animStartIndex"],
                                     f, "{0:s}_anim_{1:03n}".format(index, f))

        texFile.close()

        self.metadata["texPath"] = str(self.texPath)

    def write_json(self):
        jsonFile = open(self.outDir / "bg.json", "wt")
        json.dump(self.metadata, jsonFile, ensure_ascii=False, indent='\t')
        jsonFile.close()

    def read(self):
        self.read_Hinf()
        self.read_Htbl()
        self.read_pal()
        self.read_tex()

        # pp.pprint(self.metadata)
        # print(self.metadata)
        self.write_json()


def main():
    cmdParser = argparse.ArgumentParser(
        description="Metal Slug XX关卡BG提取、<s>重建</s>工具。")
    modeParser = cmdParser.add_subparsers(dest="mode", help="使用模式")

    readParser = modeParser.add_parser("read", help="读取模式")
    readParser.add_argument("--Hinf", action="extend", nargs="+",
                            required=True, help="Hinf文件路径(所有)", dest="HinfPathList", type=Path)
    readParser.add_argument("--Htbl", action="extend", nargs="+",
                            required=True, help="Htbl文件路径(所有)", dest="HtblPathList", type=Path)
    readParser.add_argument("--pal", help="pal文件路径",
                            dest="palPath", type=Path, required=True)
    readParser.add_argument("--tex", help="tex文件路径",
                            dest="texPath", type=Path, required=True)
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
