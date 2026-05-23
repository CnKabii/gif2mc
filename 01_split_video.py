#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
splitVideo.py

一键用 ffmpeg 把视频 / GIF 切成 Minecraft 动态地图用的 128x128 PNG 帧。

默认：
  输入：运行时询问
  输出：in/frame_00001.png ...
  fps：10
  模式：pad，保持完整画面，补边到 128x128

依赖：
  1. 安装 ffmpeg，并确保 ffmpeg 在 PATH 里
  2. Python 3.8+

用法：
  直接运行：
    python splitVideo.py

  也支持命令行：
    python splitVideo.py --input video.mp4 --fps 10 --mode pad
    python splitVideo.py --input video.mp4 --fps 12 --mode crop
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def ask_str(prompt: str, default: str | None = None) -> str:
    if default is None:
        while True:
            raw = input(f"{prompt}: ").strip().strip('"')
            if raw:
                return raw
            print("不能为空。")
    raw = input(f"{prompt} [{default}]: ").strip().strip('"')
    return default if raw == "" else raw


def ask_float(prompt: str, default: float) -> float:
    while True:
        raw = input(f"{prompt} [{default:g}]: ").strip()
        if raw == "":
            return default
        try:
            value = float(raw)
            if value <= 0:
                print("请输入大于 0 的数字。")
                continue
            return value
        except ValueError:
            print("请输入数字，比如 10 或 12.5。")


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


def ask_mode(default: str = "pad") -> str:
    print("画面模式：")
    print("  1 = pad  保留完整画面，补边到 128x128")
    print("  2 = crop 铺满地图，裁掉多余边缘")
    while True:
        raw = input("选择模式 [1/pad]: ").strip().lower()
        if raw == "":
            return default
        if raw in {"1", "pad", "p"}:
            return "pad"
        if raw in {"2", "crop", "c"}:
            return "crop"
        print("请输入 1/pad 或 2/crop。")


def ensure_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(
            "找不到 ffmpeg。\n"
            "请先安装 ffmpeg，并确保可以在命令行里直接运行 ffmpeg。\n"
            "测试方法：打开 cmd，输入 ffmpeg -version"
        )
    return ffmpeg


def build_filter(fps: float, mode: str, contrast: float, saturation: float) -> str:
    filters: list[str] = [f"fps={fps:g}"]

    if contrast != 1.0 or saturation != 1.0:
        filters.append(f"eq=contrast={contrast:g}:saturation={saturation:g}")

    if mode == "crop":
        filters.append("scale=128:128:force_original_aspect_ratio=increase")
        filters.append("crop=128:128")
    else:
        filters.append("scale=128:128:force_original_aspect_ratio=decrease")
        filters.append("pad=128:128:(ow-iw)/2:(oh-ih)/2")

    return ",".join(filters)


def clear_old_frames(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for p in output_dir.glob("*.png"):
        if p.is_file():
            p.unlink()


def run_ffmpeg(
    input_path: Path,
    output_dir: Path,
    fps: float,
    mode: str,
    clear: bool,
    contrast: float,
    saturation: float,
) -> None:
    ffmpeg = ensure_ffmpeg()

    if not input_path.exists():
        raise FileNotFoundError(f"找不到输入文件：{input_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    if clear:
        clear_old_frames(output_dir)

    vf = build_filter(fps, mode, contrast, saturation)
    output_pattern = output_dir / "frame_%05d.png"

    cmd = [
        ffmpeg,
        "-y",
        "-i", str(input_path),
        "-vf", vf,
        str(output_pattern),
    ]

    print()
    print("即将执行 ffmpeg：")
    print(" ".join(f'"{x}"' if " " in x else x for x in cmd))
    print()

    subprocess.run(cmd, check=True)

    frames = sorted(output_dir.glob("frame_*.png"))
    print()
    print("完成。")
    print(f"输出目录：{output_dir}")
    print(f"生成帧数：{len(frames)}")
    if frames:
        print(f"第一帧：{frames[0].name}")
        print(f"最后一帧：{frames[-1].name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="用 ffmpeg 一键切分视频/GIF 到 in/frame_*.png")
    parser.add_argument("--input", "-i", help="输入视频/GIF 文件路径")
    parser.add_argument("--output", "-o", default="in", help="输出文件夹，默认 in")
    parser.add_argument("--fps", type=float, default=10, help="每秒输出帧数，默认 10")
    parser.add_argument("--mode", choices=["pad", "crop"], default="pad", help="pad=保留完整画面补边；crop=铺满裁剪")
    parser.add_argument("--contrast", type=float, default=1.0, help="对比度，默认 1.0；地图画可试 1.15")
    parser.add_argument("--saturation", type=float, default=1.0, help="饱和度，默认 1.0；地图画可试 1.2")
    parser.add_argument("--no-clear", action="store_true", help="不清空输出目录旧 PNG")
    parser.add_argument("--yes", action="store_true", help="非交互模式，直接使用参数")
    args = parser.parse_args()

    if not args.yes:
        print("=== 视频/GIF 切帧工具：ffmpeg -> in/frame_*.png ===")
        print("直接回车使用方括号里的默认值。")
        print()

        if not args.input:
            args.input = ask_str("输入视频/GIF 路径")
        else:
            args.input = ask_str("输入视频/GIF 路径", args.input)

        args.fps = ask_float("fps，每秒切几帧", args.fps)
        args.mode = ask_mode(args.mode)

        use_enhance = ask_bool("是否增强对比度/饱和度（地图画可能更清楚）", False)
        if use_enhance:
            args.contrast = ask_float("对比度 contrast", 1.15)
            args.saturation = ask_float("饱和度 saturation", 1.2)

        clear = ask_bool("生成前清空 in/ 里的旧 PNG", not args.no_clear)
        args.no_clear = not clear
        print()

    if not args.input:
        raise ValueError("没有指定输入文件。")

    run_ffmpeg(
        input_path=Path(args.input),
        output_dir=Path(args.output),
        fps=args.fps,
        mode=args.mode,
        clear=not args.no_clear,
        contrast=args.contrast,
        saturation=args.saturation,
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
