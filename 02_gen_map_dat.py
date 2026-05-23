#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
读取 in/ 文件夹中的图片帧，生成 Minecraft Java 1.16.5 可用的：
  out/data/map_*.dat
  out/data/idcounts.dat

依赖：
  pip install pillow

常用：
  直接双击或运行：python genDat.py
  脚本会询问 start-index、x-center、z-center、是否清理旧 map 文件。
  也仍然支持命令行参数，例如：genDat.py --start-index 0 --x-center 0
"""

from __future__ import annotations

import argparse
import gzip
import re
import struct
from pathlib import Path
from typing import Iterable

from PIL import Image


# Minecraft Java 1.16.5 地图基础色。base id 0 是透明/空色，映射图片时跳过。
BASE_COLORS: list[tuple[int, int, int]] = [
    (0, 0, 0),
    (127, 178, 56), (247, 233, 163), (199, 199, 199), (255, 0, 0),
    (160, 160, 255), (167, 167, 167), (0, 124, 0), (255, 255, 255),
    (164, 168, 184), (151, 109, 77), (112, 112, 112), (64, 64, 255),
    (143, 119, 72), (255, 252, 245), (216, 127, 51), (178, 76, 216),
    (102, 153, 216), (229, 229, 51), (127, 204, 25), (242, 127, 165),
    (76, 76, 76), (153, 153, 153), (76, 127, 153), (127, 63, 178),
    (51, 76, 178), (102, 76, 51), (102, 127, 51), (153, 51, 51),
    (25, 25, 25), (250, 238, 77), (92, 219, 213), (74, 128, 255),
    (0, 217, 58), (129, 86, 49), (112, 2, 0), (209, 177, 161),
    (159, 82, 36), (149, 87, 108), (112, 108, 138), (186, 133, 36),
    (103, 117, 53), (160, 77, 78), (57, 41, 35), (135, 107, 98),
    (87, 92, 92), (122, 73, 88), (76, 62, 92), (76, 50, 35),
    (76, 82, 42), (142, 60, 46), (37, 22, 16), (189, 48, 49),
    (148, 63, 97), (92, 25, 29), (22, 126, 134), (58, 142, 140),
    (86, 44, 62), (20, 180, 133),
]

# Java 地图颜色每个 base color 有四档明度。颜色值 = base_id * 4 + shade_id。
SHADES = [180, 220, 255, 135]

PALETTE: list[tuple[int, tuple[int, int, int]]] = []
for base_id, rgb in enumerate(BASE_COLORS):
    if base_id == 0:
        continue
    for shade_id, mult in enumerate(SHADES):
        value = base_id * 4 + shade_id
        shaded = tuple((c * mult) // 255 for c in rgb)
        PALETTE.append((value, shaded))
PALETTE.sort(key=lambda item: item[0])

_COLOR_CACHE: dict[tuple[int, int, int], int] = {}


# NBT tag ids
TAG_END = 0
TAG_BYTE = 1
TAG_INT = 3
TAG_BYTE_ARRAY = 7
TAG_STRING = 8
TAG_LIST = 9
TAG_COMPOUND = 10

# Minecraft Java 1.16.5 DataVersion
DATA_VERSION_1_16_5 = 2586


def natural_key(path: Path) -> list[object]:
    """让 frame_2.png 排在 frame_10.png 前面。"""
    parts = re.split(r"(\d+)", path.name.lower())
    return [int(p) if p.isdigit() else p for p in parts]


def write_name(name: str) -> bytes:
    raw = name.encode("utf-8")
    return struct.pack(">H", len(raw)) + raw


def tag_byte(name: str, value: int) -> bytes:
    return bytes([TAG_BYTE]) + write_name(name) + struct.pack(">b", value)


def tag_int(name: str, value: int) -> bytes:
    return bytes([TAG_INT]) + write_name(name) + struct.pack(">i", value)


def tag_string(name: str, value: str) -> bytes:
    raw = value.encode("utf-8")
    return bytes([TAG_STRING]) + write_name(name) + struct.pack(">H", len(raw)) + raw


def tag_byte_array(name: str, data: bytes) -> bytes:
    return bytes([TAG_BYTE_ARRAY]) + write_name(name) + struct.pack(">i", len(data)) + data


def tag_empty_list(name: str, element_type: int = TAG_COMPOUND) -> bytes:
    return bytes([TAG_LIST]) + write_name(name) + bytes([element_type]) + struct.pack(">i", 0)


def tag_compound(name: str, payload: bytes) -> bytes:
    return bytes([TAG_COMPOUND]) + write_name(name) + payload + bytes([TAG_END])


def root_compound(payload: bytes) -> bytes:
    # 根 compound 名字为空。
    return bytes([TAG_COMPOUND]) + struct.pack(">H", 0) + payload + bytes([TAG_END])


def nearest_map_value(r: int, g: int, b: int) -> int:
    """把 RGB 映射到最接近的 Java 1.16.5 地图颜色值。"""
    # 压缩一点 key，缓存命中率高，画质影响很小。
    key = (r >> 2, g >> 2, b >> 2)
    cached = _COLOR_CACHE.get(key)
    if cached is not None:
        return cached

    best_value = 0
    best_distance = 10**18
    for value, (pr, pg, pb) in PALETTE:
        dr, dg, db = r - pr, g - pg, b - pb
        # 人眼对绿色更敏感，做一点加权。
        distance = 30 * dr * dr + 59 * dg * dg + 11 * db * db
        if distance < best_distance:
            best_distance = distance
            best_value = value

    _COLOR_CACHE[key] = best_value
    return best_value


def image_to_map_colors(image_path: Path, size: int = 128) -> bytes:
    """读取图片，输出 128x128 地图 colors 字节数组。"""
    with Image.open(image_path) as img:
        if img.mode != "RGBA":
            img = img.convert("RGBA")

        # 透明区域铺白底。GIF/PNG 透明帧不处理会很容易出怪颜色。
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        bg.alpha_composite(img)
        img = bg.convert("RGB")

        if img.size != (size, size):
            img = img.resize((size, size), Image.Resampling.LANCZOS)

        pixels = img.load()
        colors = bytearray(size * size)
        for y in range(size):
            for x in range(size):
                r, g, b = pixels[x, y]
                colors[y * size + x] = nearest_map_value(r, g, b)
        return bytes(colors)


def make_map_dat(colors: bytes, x_center: int, z_center: int, dimension: str) -> bytes:
    """生成 map_N.dat 的未压缩 NBT 数据。"""
    if len(colors) != 128 * 128:
        raise ValueError(f"colors 长度必须是 16384，当前是 {len(colors)}")

    data_payload = b"".join([
        tag_byte("scale", 0),
        tag_byte("trackingPosition", 1),
        tag_byte("unlimitedTracking", 0),
        tag_byte("locked", 1),
        tag_int("xCenter", x_center),
        tag_int("zCenter", z_center),
        tag_string("dimension", dimension),
        tag_empty_list("banners", TAG_COMPOUND),
        tag_empty_list("frames", TAG_COMPOUND),
        tag_byte_array("colors", colors),
    ])
    return root_compound(tag_compound("data", data_payload))


def make_idcounts_dat(next_map_id: int) -> bytes:
    """
    生成 idcounts.dat 的未压缩 NBT 数据。

    Java 1.16.5 里 out/data/idcounts.dat 通常长这样：
      root
        DataVersion: 2586
        data:
          map: <下一个地图 id>
    如果生成 map_0.dat ~ map_38.dat，这里就是 map: 39。
    """
    data_payload = tag_int("map", next_map_id)
    payload = b"".join([
        tag_int("DataVersion", DATA_VERSION_1_16_5),
        tag_compound("data", data_payload),
    ])
    return root_compound(payload)


def gzip_write(path: Path, raw_nbt: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wb", compresslevel=9) as f:
        f.write(raw_nbt)


def collect_images(input_dir: Path, patterns: Iterable[str]) -> list[Path]:
    images: list[Path] = []
    for pattern in patterns:
        images.extend(input_dir.glob(pattern))
    # 去重后自然排序
    unique = sorted(set(images), key=natural_key)
    return [p for p in unique if p.is_file()]



def ask_int(prompt: str, default: int) -> int:
    """交互式询问整数；直接回车使用默认值。"""
    while True:
        raw = input(f"{prompt} [{default}]: ").strip()
        if raw == "":
            return default
        try:
            return int(raw)
        except ValueError:
            print("请输入整数，或者直接回车使用默认值。")



def ask_bool(prompt: str, default: bool) -> bool:
    """交互式询问 yes/no；直接回车使用默认值。"""
    default_text = "Y/n" if default else "y/N"
    while True:
        raw = input(f"{prompt} [{default_text}]: ").strip().lower()
        if raw == "":
            return default
        if raw in {"y", "yes", "是", "对", "1", "true"}:
            return True
        if raw in {"n", "no", "否", "不", "0", "false"}:
            return False
        print("请输入 y 或 n，或者直接回车使用默认值。")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="从 in/ 图片帧生成 Minecraft Java 1.16.5 可用的 map_*.dat 和 idcounts.dat"
    )
    parser.add_argument("--input", "-i", default="in", help="输入图片文件夹，默认 in")
    parser.add_argument("--output", "-o", default="out/data", help="输出 data 文件夹，默认 out/data")
    parser.add_argument("--start-index", type=int, default=0, help="起始地图编号，默认 0")
    parser.add_argument("--x-center", type=int, default=0, help="地图 xCenter，默认 0")
    parser.add_argument("--z-center", type=int, default=0, help="地图 zCenter，默认 0")
    parser.add_argument(
        "--patterns",
        nargs="+",
        default=["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.webp"],
        help="输入图片匹配模式，默认支持 png/jpg/jpeg/bmp/webp",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="不删除输出目录里已有的 map_*.dat。默认会清理旧 map 文件，避免残留。",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="非交互模式：不询问，直接使用命令行参数/默认值。",
    )
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)

    # input/output 不参与询问；其余常用参数默认进入交互式询问。
    if not args.yes:
        print("=== Minecraft Java 1.16.5 map_*.dat 生成器 ===")
        print(f"输入目录固定为：{input_dir}")
        print(f"输出目录固定为：{output_dir}")
        print("直接回车使用方括号里的默认值。\n")
        args.start_index = ask_int("起始地图编号 start-index", args.start_index)
        args.x_center = ask_int("地图中心 x-center", args.x_center)
        args.z_center = ask_int("地图中心 z-center", args.z_center)
        clean_old = ask_bool("生成前清理输出目录里旧的 map_*.dat", not args.no_clean)
        args.no_clean = not clean_old
        print()

    if not input_dir.exists():
        raise FileNotFoundError(f"找不到输入目录：{input_dir}")

    frames = collect_images(input_dir, args.patterns)
    if not frames:
        raise FileNotFoundError(f"在 {input_dir} 里没有找到图片：{', '.join(args.patterns)}")

    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.no_clean:
        for old_map in output_dir.glob("map_*.dat"):
            old_map.unlink()

    print(f"输入目录：{input_dir}")
    print(f"输出目录：{output_dir}")
    print(f"帧数量：{len(frames)}")
    print(f"地图编号：map_{args.start_index}.dat 到 map_{args.start_index + len(frames) - 1}.dat")

    for index, frame_path in enumerate(frames):
        map_id = args.start_index + index
        colors = image_to_map_colors(frame_path)
        raw_map_nbt = make_map_dat(colors, args.x_center, args.z_center, "minecraft:overworld")
        out_path = output_dir / f"map_{map_id}.dat"
        gzip_write(out_path, raw_map_nbt)
        print(f"[{index + 1:>4}/{len(frames)}] {frame_path.name} -> {out_path.name}")

    next_map_id = args.start_index + len(frames)
    gzip_write(output_dir / "idcounts.dat", make_idcounts_dat(next_map_id))
    print(f"已生成 idcounts.dat，data.map = {next_map_id}")


if __name__ == "__main__":
    main()
    try:
        input("按回车退出...")
    except EOFError:
        pass
