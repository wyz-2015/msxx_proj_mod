# -*- coding: utf-8 -*-
"""
PSP 纹理 swizzle / unswizzle 的 Python3(numpy) 实现
====================================================

算法来源: Rainbow 项目 (github.com/marco-calautti/Rainbow, GPL-2.0)
  - Rainbow.ImgLib/Filters/SwizzleFilter.cs
        SwizzleFilter(width, height, bitDepth)
            : TileFilter(bitDepth, tileWidth=16, tileHeight=8, width, height)
        { TileDimensionsAsBytes = true; }
  - Rainbow.ImgLib/Filters/TileFilter.cs
        ApplyFilter()  = swizzle    (线性图像 -> PSP 瓦片流)
        Defilter()     = unswizzle  (PSP 瓦片流 -> 线性图像)

原理 (PSP 图形硬件的纹理排列方式):
  图像按行展开为字节流后, 以 "16 字节 x 8 行" 的瓦片(tile)为单位重新排列:
  - 瓦片内部按行优先顺序存放;
  - 每行字节数向上补齐到 16 的倍数, 行数向上补齐到 8 的倍数;
  - 补齐区域在 swizzle 流中占据位置, 内容填 0 (Defilter 时读取后丢弃)。

本模块将上述四层嵌套循环改写为 numpy 向量化索引, 结果与 C# 原版逐字节一致
(已用参考实现对拍验证, 见 __main__ 中的自测)。
"""

from __future__ import annotations

import numpy as np

# ---- Rainbow  swizzle 参数 -------------------------------------------------
TILE_W_BYTES = 16  # 瓦片宽度(字节)。TileFilter tileWidth=16 且 TileDimensionsAsBytes=True
TILE_H = 8         # 瓦片高度(行)。TileFilter tileHeight=8

__all__ = ["unswizzle", "swizzle", "swizzle_to_stream"]


# ---- 内部工具 ----------------------------------------------------------------
def _round_up(v: int, m: int) -> int:
    return (v + m - 1) // m * m


def _check_bpp(bpp: int) -> None:
    if bpp not in (4, 8, 16, 32):
        raise ValueError(f"不支持的 bpp={bpp}, 仅支持 4 / 8 / 16 / 32")


def _pixels_to_bytes(data: np.ndarray, bpp: int) -> np.ndarray:
    """一维像素数组 -> 一维 uint8 字节视图。

    bpp=4 时 data 为打包半字节流(uint8, 每字节两个像素, 低半字节在左);
    其余 bpp 要求 dtype 与之一一对应(uint8 / uint16 / uint32)。
    """
    arr = np.ascontiguousarray(data).ravel()
    if bpp == 4:
        if arr.dtype != np.uint8:
            raise ValueError("bpp=4 时 data 必须是 uint8(打包半字节流)")
        return arr
    need = bpp // 8
    if arr.dtype.itemsize != need:
        raise ValueError(
            f"bpp={bpp} 要求 dtype 为 uint{bpp}(itemsize={need}), 实际为 {arr.dtype}"
        )
    return arr.view(np.uint8)


def _bytes_to_pixels(img: np.ndarray, width: int, bpp: int) -> np.ndarray:
    """(height, row_bytes) 的 uint8 字节矩阵 -> (height, width) 像素矩阵。"""
    height, row_bytes = img.shape
    if bpp == 8:
        return img
    if bpp in (16, 32):  # PSP 为小端
        dt = np.dtype(f"<u{bpp // 8}")
        return np.ascontiguousarray(img).view(dt).reshape(height, width)
    # bpp == 4: 每字节两个像素, 低半字节在左
    out = np.empty((height, row_bytes * 2), dtype=np.uint8)
    out[:, 0::2] = img & 0x0F
    out[:, 1::2] = img >> 4
    return out[:, :width]


def _tile_index_grid(row_bytes: int, height: int):
    """构造 swizzle 偏移映射。

    返回 (idx, W, H, yy, xx):
      idx[y, x] = 字节 (y, x) 在 swizzled 流中的偏移(即 C# 中计数器 i 的值);
      W = 行字节数补齐到 16 的倍数; H = 行数补齐到 8 的倍数。
    """
    W = _round_up(row_bytes, TILE_W_BYTES)
    H = _round_up(height, TILE_H)
    yy, xx = np.meshgrid(
        np.arange(H, dtype=np.int64), np.arange(W, dtype=np.int64), indexing="ij"
    )
    tiles_per_row = W // TILE_W_BYTES
    idx = (
        (yy // TILE_H) * tiles_per_row + (xx // TILE_W_BYTES)
    ) * (TILE_H * TILE_W_BYTES) + (yy % TILE_H) * TILE_W_BYTES + (xx % TILE_W_BYTES)
    return idx, W, H, yy, xx


# ---- 入口函数 -----------------------------------------------------------------
def unswizzle(width: int, height: int, data: np.ndarray, bpp: int = 8) -> np.ndarray:
    """PSP 反 swizzle (Rainbow TileFilter.Defilter)。

    将 PSP 打乱的(swizzled)图像数据还原为正常的 (height, width) 图像。

    参数:
        width, height: 图像尺寸(像素)。
        data:          一维 ndarray, PSP swizzled 数据。
                       bpp=8/16/32 时每个元素为一个像素(uint8/uint16/uint32);
                       bpp=4 时为打包半字节流(uint8)。
                       长度需 >= 补齐后的流大小
                       (行字节向上取整到 16, 行数向上取整到 8)。
        bpp:           每像素位数, 取 4 / 8 / 16 / 32, 默认 8。

    返回:
        np.ndarray, 形状 (height, width), dtype 与输入像素一致
        (bpp=4 时返回展开后的 uint8 像素索引)。
    """
    _check_bpp(bpp)
    if width <= 0 or height <= 0:
        return np.empty((max(height, 0), max(width, 0)), dtype=np.uint8)

    row_bytes = width * bpp // 8  # Rainbow: (width * bpp) / 8
    raw = _pixels_to_bytes(data, bpp)
    idx, W, H, _, _ = _tile_index_grid(row_bytes, height)

    need = W * H
    if raw.size < need:
        raise ValueError(
            f"data 长度不足: swizzled 流需要 {need} 字节"
            f"(行补齐到 {W} 字节, 高补齐到 {H} 行), 实际 {raw.size} 字节"
        )

    stream = raw[:need]
    # 向量化等价于 Defilter 的四层循环:
    #   每个图像坐标 (y,x) 直接取流中偏移 idx[y,x]; 补齐字节被丢弃
    img_bytes = stream[idx.ravel()].reshape(H, W)[:height, :row_bytes]
    return _bytes_to_pixels(img_bytes, width, bpp)


def swizzle(width: int, height: int, data: np.ndarray, bpp: int = 8) -> np.ndarray:
    """PSP 正向 swizzle (Rainbow TileFilter.ApplyFilter) 的 (height, width) 形式。

    返回按 16 字节 x 8 行瓦片顺序重排后的图像数据, 形状 (height, width)。
    注意: 为符合 (height, width) 的形状约定, 结果不含补齐用的填充零;
    若需要写入文件的、含补齐的标准 PSP 纹理字节流, 请使用 swizzle_to_stream()。
    """
    _check_bpp(bpp)
    if width <= 0 or height <= 0:
        return np.empty((max(height, 0), max(width, 0)), dtype=np.uint8)

    row_bytes = width * bpp // 8
    stream = swizzle_to_stream(width, height, data, bpp)
    idx, W, H, yy, xx = _tile_index_grid(row_bytes, height)
    valid = (yy < height) & (xx < row_bytes)
    out_bytes = stream[idx[valid]]  # 长度 = row_bytes * height, tile 顺序
    return _bytes_to_pixels(out_bytes.reshape(height, row_bytes), width, bpp)


def swizzle_to_stream(width: int, height: int, data: np.ndarray, bpp: int = 8) -> np.ndarray:
    """PSP 正向 swizzle, 返回完整补齐的标准 swizzled 字节流(1D, uint8)。

    流大小 = ceil(width*bpp/8 / 16) * 16 * ceil(height / 8) * 8 字节,
    与 Rainbow ApplyFilter 的输出逐字节一致(已对拍验证)。
    """
    _check_bpp(bpp)
    row_bytes = width * bpp // 8
    flat = _pixels_to_bytes(data, bpp)
    if flat.size < row_bytes * height:
        raise ValueError(
            f"data 长度不足: 需要 {row_bytes * height} 字节, 实际 {flat.size} 字节"
        )
    flat = flat[: row_bytes * height]

    idx, W, H, yy, xx = _tile_index_grid(row_bytes, height)
    valid = (yy < height) & (xx < row_bytes)
    padded = np.zeros(W * H, dtype=np.uint8)  # 越界处填 0, 但仍占据流中的位置
    padded[idx[valid]] = flat
    return padded


# ---- 自测 ----------------------------------------------------------------------
if __name__ == "__main__":
    rng = np.random.default_rng(42)

    def _ref_defilter(w, h, data, bpp=8):  # C# Defilter 的直接翻译(对拍用)
        row = w * bpp // 8
        buf = np.zeros(row * h, np.uint8)
        src = np.asarray(data, np.uint8).ravel()
        i = 0
        for y in range(0, h, TILE_H):
            for x in range(0, row, TILE_W_BYTES):
                for ty in range(y, y + TILE_H):
                    for tx in range(x, x + TILE_W_BYTES):
                        d = src[i]
                        i += 1
                        if tx >= row or ty >= h:
                            continue
                        buf[ty * row + tx] = d
        return buf.reshape(h, row)

    # 1) unswizzle 与 C# Defilter 逐字节对拍
    for h, w in [(37, 100), (8, 16), (5, 3), (512, 512), (272, 480), (33, 17)]:
        Wp, Hp = _round_up(w, 16), _round_up(h, 8)
        data = rng.integers(0, 256, Wp * Hp, dtype=np.uint8)
        assert np.array_equal(unswizzle(w, h, data), _ref_defilter(w, h, data))
    print("1) unswizzle 与 Rainbow Defilter 逐字节一致 ✔")

    # 2) swizzle -> unswizzle 往返还原(4/8/16/32 bpp, 非整除尺寸)
    for bpp, dt in [(8, np.uint8), (16, np.uint16), (32, np.uint32)]:
        h, w = 37, 100
        img = rng.integers(0, 2 ** bpp, (h, w), dtype=dt)
        assert np.array_equal(unswizzle(w, h, swizzle_to_stream(w, h, img, bpp), bpp), img)
        # swizzle() 返回去补齐的 (h, w) 形式, 内容应与 swizzle_to_stream 的实像素一致
        stream = swizzle_to_stream(w, h, img, bpp)
        idx, W, H, yy, xx = _tile_index_grid(w * bpp // 8, h)
        valid = (yy < h) & (xx < w * bpp // 8)
        assert np.array_equal(swizzle(w, h, img, bpp).ravel().view(np.uint8), stream[idx[valid]])
    h, w = 37, 100
    img4 = rng.integers(0, 16, (h, w), dtype=np.uint8)
    packed = (img4[:, 0::2] | (img4[:, 1::2] << 4)).astype(np.uint8).ravel()
    assert np.array_equal(unswizzle(w, h, swizzle_to_stream(w, h, packed, 4), 4), img4)
    print("2) swizzle <-> unswizzle 往返一致 (bpp=4/8/16/32) ✔")
