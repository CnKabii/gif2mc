#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
04_split_tiles.py

把 01_split_video.py 输出的大帧 PNG 序列切成有序的 128x128 tile PNG 序列。

用途：
  当屏幕大于 1x1 时，例如 width_maps=3, height_maps=2，
  01 会输出 384x256 的大帧：
    in/frame_00001.png
    in/frame_00002.png
    ...

  04 会把每张大帧按“从左到右、从上到下”的顺序切成 128x128 tile，
  并输出为一条线性的 frame_*.png 序列，方便 02_gen_map_dat.py 原样读取。

推荐工作流：
  直接把 tile 输出回 in/，这样下一步 02 可以继续读取 in/，不用手动覆盖：
    python 04_split_tiles.py --input in --width-maps 3 --height-maps 2 --replace-input --yes

  使用 --replace-input 时，04 会先把原来的大帧移动到备份目录，例如 in_big_frames/，
  然后把切好的 tile 序列写回 in/。

普通工作流：
    python 04_split_tiles.py --input in --output tiles --width-maps 3 --height-maps 2 --yes

后续：
  python 02_gen_map_dat.py --input in ...      # replace-input 模式
  python 02_gen_map_dat.py --input tiles ...   # 普通输出模式
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from PIL import Image


TILE_SIZE = 128


def ask_str(prompt: str, default: str | None = None) -> str:
    if default is None:
        while True:
            raw = input(f"{prompt}: ").strip().strip('"')
            if raw:
                return raw
            print("不能为空。")
    raw = input(f"{prompt} [{default}]: ").strip().strip('"')
    return default if raw == "" else raw


def ask_int(prompt: str, default: int) -> int:
    while True:
        raw = input(f"{prompt} [{default}]: ").strip()
        if raw == "":
            return default
        try:
            value = int(raw)
            if value <= 0:
                print("请输入大于 0 的整数。")
                continue
            return value
        except ValueError:
            print("请输入整数，比如 1、2、3。")


def ask_bool(prompt: str, default: bool) -> bool:
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


def clear_old_frames(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for p in output_dir.glob("*.png"):
        if p.is_file():
            p.unlink()


def list_input_frames(input_dir: Path) -> list[Path]:
    frames = sorted(input_dir.glob("frame_*.png"))
    if not frames:
        raise FileNotFoundError(f"输入目录里没有找到 frame_*.png：{input_dir}")
    return frames


def unique_backup_dir(input_dir: Path, requested_backup_dir: Path | None = None) -> Path:
    """
    返回一个不会覆盖已有内容的备份目录。
    默认：in -> in_big_frames；如果已存在，则自动追加 _2、_3 ...
    """
    if requested_backup_dir is not None:
        base = requested_backup_dir
    else:
        base = input_dir.with_name(f"{input_dir.name}_big_frames")

    if not base.exists():
        return base

    index = 2
    while True:
        candidate = base.with_name(f"{base.name}_{index}")
        if not candidate.exists():
            return candidate
        index += 1


def move_input_frames_to_backup(input_dir: Path, backup_dir: Path) -> Path:
    """
    把 input_dir 里的 frame_*.png 移动到 backup_dir。
    这样 output_dir 可以安全地继续使用原 input_dir，方便 02 直接读取。
    """
    frames = list_input_frames(input_dir)
    backup_dir.mkdir(parents=True, exist_ok=False)

    for frame in frames:
        shutil.move(str(frame), str(backup_dir / frame.name))

    return backup_dir


def split_one_frame(
    frame_path: Path,
    output_dir: Path,
    width_maps: int,
    height_maps: int,
    next_index: int,
) -> int:
    expected_width = width_maps * TILE_SIZE
    expected_height = height_maps * TILE_SIZE

    with Image.open(frame_path) as img:
        img = img.convert("RGB")
        if img.size != (expected_width, expected_height):
            raise ValueError(
                f"{frame_path.name} 尺寸不匹配：期望 {expected_width}x{expected_height}，实际 {img.size[0]}x{img.size[1]}。\n"
                "请检查 01_split_video.py 的 width-maps / height-maps 参数是否一致。"
            )

        for row in range(height_maps):
            for col in range(width_maps):
                left = col * TILE_SIZE
                top = row * TILE_SIZE
                tile = img.crop((left, top, left + TILE_SIZE, top + TILE_SIZE))
                tile.save(output_dir / f"frame_{next_index:06d}.png")
                next_index += 1

    return next_index


def split_all_frames(
    input_dir: Path,
    output_dir: Path,
    width_maps: int,
    height_maps: int,
    clear: bool,
) -> None:
    if width_maps <= 0 or height_maps <= 0:
        raise ValueError("width-maps 和 height-maps 必须是大于 0 的整数。")

    frames = list_input_frames(input_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if clear:
        clear_old_frames(output_dir)

    tile_count = width_maps * height_maps
    next_index = 1

    print()
    print(f"输入目录：{input_dir}")
    print(f"输出目录：{output_dir}")
    print(f"屏幕尺寸：{width_maps}x{height_maps}")
    print(f"每帧 tile 数：{tile_count}")
    print(f"大帧数量：{len(frames)}")
    print()

    for i, frame_path in enumerate(frames, start=1):
        next_index = split_one_frame(frame_path, output_dir, width_maps, height_maps, next_index)
        if i == 1 or i == len(frames) or i % 50 == 0:
            print(f"已处理 {i}/{len(frames)}：{frame_path.name}")

    output_frames = sorted(output_dir.glob("frame_*.png"))
    print()
    print("完成。")
    print(f"输出 tile 图片数：{len(output_frames)}")
    if output_frames:
        print(f"第一张：{output_frames[0].name}")
        print(f"最后一张：{output_frames[-1].name}")
    print()
    print("下一步可以把输出目录交给 02_gen_map_dat.py。")


def main() -> None:
    parser = argparse.ArgumentParser(description="把大帧 PNG 序列切成有序 128x128 tile PNG 序列")
    parser.add_argument("--input", "-i", default="in", help="输入大帧目录，默认 in")
    parser.add_argument("--output", "-o", default="tiles", help="输出 tile 目录，默认 tiles")
    parser.add_argument("--width-maps", type=int, default=1, help="屏幕宽度，单位为地图/展示框，默认 1")
    parser.add_argument("--height-maps", type=int, default=1, help="屏幕高度，单位为地图/展示框，默认 1")
    parser.add_argument("--replace-input", action="store_true", help="把原输入大帧备份后，将 tile 序列输出回输入目录，方便 02 直接读取")
    parser.add_argument("--backup-dir", default=None, help="replace-input 模式的大帧备份目录，默认 input_big_frames")
    parser.add_argument("--no-clear", action="store_true", help="不清空输出目录旧 PNG")
    parser.add_argument("--yes", action="store_true", help="非交互模式，直接使用参数")
    args = parser.parse_args()

    if not args.yes:
        print("=== 大帧切 tile 工具：大帧 PNG -> 有序 128x128 PNG ===")
        print("直接回车使用方括号里的默认值。")
        print()

        args.input = ask_str("输入大帧目录", args.input)
        args.width_maps = ask_int("屏幕宽度 width，单位为地图/展示框", args.width_maps)
        args.height_maps = ask_int("屏幕高度 height，单位为地图/展示框", args.height_maps)

        if args.width_maps == 1 and args.height_maps == 1:
            print()
            print("检测到屏幕尺寸是 1x1，其实不需要运行 04。")
            still_run = ask_bool("仍然继续切分", False)
            if not still_run:
                return

        args.replace_input = ask_bool("把 tile 直接输出回输入目录，方便 02 继续读取", True)
        if args.replace_input:
            args.output = args.input
            args.backup_dir = ask_str("原大帧备份目录", f"{Path(args.input).name}_big_frames")
            args.no_clear = False
        else:
            args.output = ask_str("输出 tile 目录", args.output)
            clear = ask_bool("生成前清空输出目录里的旧 PNG", not args.no_clear)
            args.no_clear = not clear
        print()

    input_dir = Path(args.input)
    output_dir = Path(args.output)

    if args.replace_input:
        requested_backup_dir = Path(args.backup_dir) if args.backup_dir else None
        if requested_backup_dir is not None and not requested_backup_dir.is_absolute():
            requested_backup_dir = input_dir.parent / requested_backup_dir

        backup_dir = unique_backup_dir(input_dir, requested_backup_dir)
        print()
        print("replace-input 模式：")
        print(f"原大帧将备份到：{backup_dir}")
        print(f"tile 序列将输出到：{input_dir}")
        print()

        input_dir = move_input_frames_to_backup(input_dir, backup_dir)
        output_dir = Path(args.input)
        # 原 frame_*.png 已经移走，可以正常写回输入目录。
        args.no_clear = False

    split_all_frames(
        input_dir=input_dir,
        output_dir=output_dir,
        width_maps=args.width_maps,
        height_maps=args.height_maps,
        clear=not args.no_clear,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print()
        print("出错了：")
        print(e)
    finally:
        try:
            input("按回车退出...")
        except EOFError:
            pass
