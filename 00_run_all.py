#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gif2Mc 一键流程入口。

它只负责编排三个独立脚本：
1. 01_split_video.py   视频/GIF -> in/frame_*.png
2. 02_gen_map_dat.py   in/frame_*.png -> out/data/map_*.dat
3. 03_gen_datapack.py  out/data/map_*.dat -> out/datapack

三个脚本仍然可以单独运行，方便排查问题。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def ask(prompt: str, default: str) -> str:
    raw = input(f"{prompt} [{default}]: ").strip().strip('"')
    return raw if raw else default


def ask_int(prompt: str, default: int) -> int:
    while True:
        raw = input(f"{prompt} [{default}]: ").strip()
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError:
            print("请输入整数。")


def ask_float(prompt: str, default: float) -> float:
    while True:
        raw = input(f"{prompt} [{default:g}]: ").strip()
        if not raw:
            return default
        try:
            return float(raw)
        except ValueError:
            print("请输入数字。")


def ask_bool(prompt: str, default: bool) -> bool:
    hint = "Y/n" if default else "y/N"
    while True:
        raw = input(f"{prompt} [{hint}]: ").strip().lower()
        if not raw:
            return default
        if raw in {"y", "yes", "是", "1", "true"}:
            return True
        if raw in {"n", "no", "否", "0", "false"}:
            return False
        print("请输入 y 或 n。")


def resolve_under_root(path_text: str) -> Path:
    """
    把相对路径统一按脚本所在目录 ROOT 解析。

    这样无论你从哪个工作目录启动 00_run_all.py，
    input.mp4、in、out 都会优先指向工具文件夹里的对应路径。
    绝对路径则原样使用。
    """
    p = Path(path_text.strip().strip('"'))
    if p.is_absolute():
        return p
    return ROOT / p


def run(cmd: list[str]) -> None:
    print()
    print("执行：")
    print(" ".join(f'"{x}"' if " " in x else x for x in cmd))
    print()
    subprocess.run(cmd, check=True, cwd=ROOT)


def main() -> None:
    parser = argparse.ArgumentParser(description="Gif2Mc 一键生成入口")
    parser.add_argument("--video", help="输入视频/GIF 文件；提供后会先切帧")
    parser.add_argument("--frames", default="in", help="图片帧目录，默认 in")
    parser.add_argument("--skip-split", action="store_true", help="跳过切帧，直接使用 --frames 目录")
    parser.add_argument("--fps", type=float, default=10, help="切帧 FPS，默认 10")
    parser.add_argument("--mode", choices=["pad", "crop"], default="pad", help="切帧模式，默认 pad")
    parser.add_argument("--start-map", type=int, default=0, help="起始 map id，默认 0")
    parser.add_argument("--x-center", type=int, default=0, help="地图 xCenter，默认 0")
    parser.add_argument("--z-center", type=int, default=0, help="地图 zCenter，默认 0")
    parser.add_argument("--x", type=int, default=0, help="展示框支撑方块 x，默认 0")
    parser.add_argument("--y", type=int, default=-60, help="展示框支撑方块 y，默认 -60")
    parser.add_argument("--z", type=int, default=0, help="展示框支撑方块 z，默认 0")
    parser.add_argument("--namespace", default="gif2mc", help="数据包命名空间，默认 gif2mc")
    parser.add_argument("--frame-delay", type=int, default=20, help="播放帧间隔 tick，默认 20")
    parser.add_argument("--out", default="out", help="输出根目录，默认 out")
    parser.add_argument("--yes", action="store_true", help="非交互模式")
    args = parser.parse_args()

    if not args.yes:
        print("=== Gif2Mc 一键流程 ===")
        print("三个脚本仍然独立保留；这个入口只是帮你按顺序调用。")
        print()

        use_video = not args.skip_split
        if not args.video:
            use_video = ask_bool("是否从视频/GIF 开始切帧", True)
        if use_video:
            args.video = ask("输入视频/GIF 路径", args.video or "video.mp4")
            args.fps = ask_float("切帧 FPS", args.fps)
            args.mode = ask("切帧模式 pad/crop", args.mode)
        else:
            args.skip_split = True

        args.frames = ask("图片帧目录", args.frames)
        args.out = ask("输出根目录", args.out)
        args.start_map = ask_int("起始 map id", args.start_map)
        args.x = ask_int("展示框支撑方块 x", args.x)
        args.y = ask_int("展示框支撑方块 y", args.y)
        args.z = ask_int("展示框支撑方块 z", args.z)
        args.namespace = ask("namespace", args.namespace)
        args.frame_delay = ask_int("frame-delay，20=每秒1帧，2=每秒10帧", args.frame_delay)

    frames_dir = resolve_under_root(args.frames)
    out_root = resolve_under_root(args.out)
    data_dir = out_root / "data"
    datapack_dir = out_root / "datapack"

    if not args.skip_split:
        if not args.video:
            raise ValueError("没有指定视频/GIF 路径。")
        video_path = resolve_under_root(args.video)
        run([
            sys.executable, str(ROOT / "01_split_video.py"),
            "--input", str(video_path),
            "--output", str(frames_dir),
            "--fps", str(args.fps),
            "--mode", args.mode,
            "--yes",
        ])

    run([
        sys.executable, str(ROOT / "02_gen_map_dat.py"),
        "--input", str(frames_dir),
        "--output", str(data_dir),
        "--start-index", str(args.start_map),
        "--x-center", str(args.x_center),
        "--z-center", str(args.z_center),
        "--yes",
    ])

    run([
        sys.executable, str(ROOT / "03_gen_datapack.py"),
        "--world-data", str(data_dir),
        "--datapack", str(datapack_dir),
        "--namespace", args.namespace,
        "--start-map", str(args.start_map),
        "--x", str(args.x),
        "--y", str(args.y),
        "--z", str(args.z),
        "--frame-delay", str(args.frame_delay),
        "--meta-dir", str(out_root),
        "--yes",
    ])

    print()
    print("全部完成。")
    print(f"地图数据：{data_dir}")
    print(f"数据包：  {datapack_dir}")
    print(f"说明文件：{out_root / 'README.txt'}")
    print(f"配置记录：{out_root / 'config.json'}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print()
        print("出错了：")
        print(e)
        raise
