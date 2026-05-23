from pathlib import Path
import json
import re
import shutil
import argparse


# =========================
# 小工具函数
# =========================

def ask(prompt: str, default: str) -> str:
    """
    交互式输入。
    直接回车则使用默认值。
    """
    value = input(f"{prompt} [{default}]: ").strip()
    return value if value else default


def ask_int(prompt: str, default: int) -> int:
    """
    交互式输入整数。
    直接回车则使用默认值。
    """
    while True:
        value = input(f"{prompt} [{default}]: ").strip()
        if not value:
            return default

        try:
            return int(value)
        except ValueError:
            print("请输入整数。")


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    """
    交互式输入 yes/no。
    """
    default_text = "Y/n" if default else "y/N"

    while True:
        value = input(f"{prompt} [{default_text}]: ").strip().lower()

        if not value:
            return default

        if value in ("y", "yes", "是", "1", "true"):
            return True

        if value in ("n", "no", "否", "0", "false"):
            return False

        print("请输入 y 或 n。")


def write_text(path: Path, text: str):
    """
    写入文本文件，自动创建父目录。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# =========================
# map_*.dat 扫描
# =========================

def scan_map_ids(world_data_dir: Path) -> list[int]:
    """
    扫描 world_data_dir 里的 map_*.dat，返回排序后的 map id 列表。
    """
    if not world_data_dir.exists():
        raise FileNotFoundError(f"找不到 world_data 文件夹：{world_data_dir}")

    pattern = re.compile(r"^map_(\d+)\.dat$")

    ids = []
    for file in world_data_dir.iterdir():
        if not file.is_file():
            continue

        match = pattern.match(file.name)
        if match:
            ids.append(int(match.group(1)))

    ids.sort()
    return ids


def get_continuous_map_ids(all_ids: list[int], start_map: int) -> list[int]:
    """
    从 start_map 开始，获取连续存在的 map id。
    如果中间断号，则只返回断号前的连续部分。
    """
    id_set = set(all_ids)
    result = []

    current = start_map
    while current in id_set:
        result.append(current)
        current += 1

    return result


# =========================
# datapack 生成
# =========================

def generate_pack_mcmeta(datapack_dir: Path, description: str):
    content = {
        "pack": {
            "pack_format": 48,
            "description": description
        }
    }

    write_text(
        datapack_dir / "pack.mcmeta",
        json.dumps(content, ensure_ascii=False, indent=2)
    )


def generate_function_tags(datapack_dir: Path, namespace: str):
    """
    生成 Minecraft 自动加载和 tick 标签。

    注意：
    这里必须放在 data/minecraft/tags/function/。
    load 和 tick 现在指向 internal/，这样用户补全 /function 时更干净。
    """
    tag_dir = datapack_dir / "data" / "minecraft" / "tags" / "function"

    load_json = {
        "values": [
            f"{namespace}:internal/load"
        ]
    }

    tick_json = {
        "values": [
            f"{namespace}:internal/tick"
        ]
    }

    write_text(
        tag_dir / "load.json",
        json.dumps(load_json, ensure_ascii=False, indent=2)
    )

    write_text(
        tag_dir / "tick.json",
        json.dumps(tick_json, ensure_ascii=False, indent=2)
    )


def generate_basic_functions(
    datapack_dir: Path,
    namespace: str,
    frame_count: int,
    start_map: int,
    x: int,
    y: int,
    z: int,
    frame_delay: int,
    use_glow_frame: bool,
):
    """
    生成 mcfunction 文件。

    根目录只保留用户常用函数：
    setup / init / init_f / start / pause / restart

    内部函数全部放入 internal/：
    load / tick / next / load_frame / init_next / init_finish
    """
    function_dir = datapack_dir / "data" / namespace / "function"
    internal_dir = function_dir / "internal"

    frame_entity = "minecraft:glow_item_frame" if use_glow_frame else "minecraft:item_frame"

    # internal/load.mcfunction
    load_content = f"""# {namespace}:internal/load
# 内部函数：数据包加载时执行
# 由 data/minecraft/tags/function/load.json 在 /reload 后自动调用
# 作用：创建本数据包需要的 scoreboard

scoreboard objectives add {namespace}.state dummy
scoreboard objectives add {namespace}.timer dummy
scoreboard objectives add {namespace}.frame dummy
"""

    # setup.mcfunction
    setup_content = f"""# {namespace}:setup
# 用户函数：初始化展示框和播放状态

function {namespace}:internal/load

scoreboard players set #playing {namespace}.state 0
scoreboard players set #timer {namespace}.timer 0
scoreboard players set #frame {namespace}.frame 0

# 放一个屏障作为展示框支撑
setblock {x} {y} {z} minecraft:barrier

# 清理旧展示框
kill @e[type={frame_entity},tag={namespace}.screen]

# 生成展示框
# 注意：Facing 方向后面可能需要根据实际朝向调整
summon {frame_entity} {x} {y} {z + 1} {{Tags:["{namespace}.screen"],Facing:3b,Item:{{id:"minecraft:filled_map",count:1,components:{{"minecraft:map_id":{start_map}}}}}}}

function {namespace}:internal/load_frame
"""

    # init.mcfunction：2 FPS 预载
    init_content = f"""# {namespace}:init
# 用户函数：慢速预载所有地图，默认 2 FPS
# 效果：从第一帧慢速播放一次，结束后回到第一帧并暂停

scoreboard players set #playing {namespace}.state 2
scoreboard players set #timer {namespace}.timer 0
scoreboard players set #frame {namespace}.frame 0
scoreboard players set #init_delay {namespace}.timer 10

function {namespace}:internal/load_frame
"""

    # init_f.mcfunction：4 FPS 预载
    init_f_content = f"""# {namespace}:init_f
# 用户函数：快速预载所有地图，默认 5 FPS
# 效果：从第一帧较快播放一次，结束后回到第一帧并暂停

scoreboard players set #playing {namespace}.state 2
scoreboard players set #timer {namespace}.timer 0
scoreboard players set #frame {namespace}.frame 0
scoreboard players set #init_delay {namespace}.timer 4

function {namespace}:internal/load_frame
"""

    # start.mcfunction
    start_content = f"""# {namespace}:start
# 用户函数：开始正常播放

scoreboard players set #playing {namespace}.state 1
"""

    # pause.mcfunction
    pause_content = f"""# {namespace}:pause
# 用户函数：暂停播放

scoreboard players set #playing {namespace}.state 0
"""

    # restart.mcfunction
    restart_content = f"""# {namespace}:restart
# 用户函数：从第一帧重新开始正常播放

scoreboard players set #playing {namespace}.state 1
scoreboard players set #timer {namespace}.timer 0
scoreboard players set #frame {namespace}.frame 0

function {namespace}:internal/load_frame
"""

    # internal/tick.mcfunction
    tick_content = f"""# {namespace}:internal/tick
# 内部函数：每 tick 自动执行
# state 0 = 暂停
# state 1 = 正常播放
# state 2 = init 预载模式

# 正常播放模式：按 frame-delay 切换下一帧
execute if score #playing {namespace}.state matches 1 run scoreboard players add #timer {namespace}.timer 1
execute if score #playing {namespace}.state matches 1 if score #timer {namespace}.timer matches {frame_delay}.. run function {namespace}:internal/next

# init 预载模式：按 #init_delay 指定的速度慢速扫一遍所有帧
execute if score #playing {namespace}.state matches 2 run scoreboard players add #timer {namespace}.timer 1
execute if score #playing {namespace}.state matches 2 if score #timer {namespace}.timer >= #init_delay {namespace}.timer run function {namespace}:internal/init_next
"""

    # internal/next.mcfunction
    next_content = f"""# {namespace}:internal/next
# 内部函数：正常播放时切换到下一帧

scoreboard players set #timer {namespace}.timer 0
scoreboard players add #frame {namespace}.frame 1

# 如果超过最后一帧，回到第一帧
execute if score #frame {namespace}.frame matches {frame_count}.. run scoreboard players set #frame {namespace}.frame 0

function {namespace}:internal/load_frame
"""

    # internal/init_next.mcfunction
    init_next_content = f"""# {namespace}:internal/init_next
# 内部函数：init 预载模式下切换到下一帧

scoreboard players set #timer {namespace}.timer 0
scoreboard players add #frame {namespace}.frame 1

# init 播放完整扫过一遍后，回到第一帧并暂停
execute if score #frame {namespace}.frame matches {frame_count}.. run function {namespace}:internal/init_finish
execute unless score #frame {namespace}.frame matches {frame_count}.. run function {namespace}:internal/load_frame
"""

    # internal/init_finish.mcfunction
    init_finish_content = f"""# {namespace}:internal/init_finish
# 内部函数：结束 init 预载模式
# 回到第一帧，并保持暂停状态

scoreboard players set #playing {namespace}.state 0
scoreboard players set #timer {namespace}.timer 0
scoreboard players set #frame {namespace}.frame 0

function {namespace}:internal/load_frame
"""

    # internal/load_frame.mcfunction
    lines = [
        f"# {namespace}:internal/load_frame",
        "# 内部函数：根据当前 #frame，把展示框里的 filled_map 切换到对应 map_id",
        ""
    ]

    for frame_index in range(frame_count):
        map_id = start_map + frame_index
        line = (
            f'execute if score #frame {namespace}.frame matches {frame_index} '
            f'run data merge entity @e[type={frame_entity},tag={namespace}.screen,limit=1,sort=nearest] '
            f'{{Item:{{id:"minecraft:filled_map",count:1,components:{{"minecraft:map_id":{map_id}}}}}}}'
        )
        lines.append(line)

    load_frame_content = "\n".join(lines) + "\n"

    # 用户函数
    write_text(function_dir / "setup.mcfunction", setup_content)
    write_text(function_dir / "init.mcfunction", init_content)
    write_text(function_dir / "init_f.mcfunction", init_f_content)
    write_text(function_dir / "start.mcfunction", start_content)
    write_text(function_dir / "pause.mcfunction", pause_content)
    write_text(function_dir / "restart.mcfunction", restart_content)

    # 内部函数
    write_text(internal_dir / "load.mcfunction", load_content)
    write_text(internal_dir / "tick.mcfunction", tick_content)
    write_text(internal_dir / "next.mcfunction", next_content)
    write_text(internal_dir / "init_next.mcfunction", init_next_content)
    write_text(internal_dir / "init_finish.mcfunction", init_finish_content)
    write_text(internal_dir / "load_frame.mcfunction", load_frame_content)



def make_output_readme(config: dict) -> str:
    namespace = config["namespace"]
    return f"""Gif2Mc 动态地图数据包生成结果

生成信息
- Minecraft: {config['minecraft']}
- namespace: {namespace}
- map 范围: map_{config['start_map']}.dat ~ map_{config['end_map']}.dat
- 帧数量: {config['frame_count']}
- 播放 frame-delay: {config['frame_delay']} tick
- init: 2 FPS 预载，扫完后回到第一帧并暂停
- init_f: 5 FPS 预载，扫完后回到第一帧并暂停
- 展示框支撑方块坐标: {config['x']} {config['y']} {config['z']}
- 展示框类型: {config['frame_entity']}

放置方式
1. 把 world data 目录里的 map_*.dat 和 idcounts.dat 复制到世界存档的 data 文件夹。
   例如：.minecraft/saves/你的世界/data/

2. 把 datapack 文件夹复制到世界存档的 datapacks 文件夹。
   注意 pack.mcmeta 必须直接位于：
   saves/你的世界/datapacks/某个名字/pack.mcmeta

游戏内命令
/reload
/function {namespace}:setup
/function {namespace}:init
/function {namespace}:init_f
/function {namespace}:start
/function {namespace}:pause
/function {namespace}:restart

命令说明
setup   创建屏幕并显示第一帧
init    2 FPS 慢速预载一遍，完成后回到第一帧并暂停
init_f  5 FPS 快速预载一遍，完成后回到第一帧并暂停
start   开始正常播放
pause   暂停播放
restart 从第一帧重新开始正常播放

调试提示
如果 /reload 没报错，但画面不动，先确认 world data 已经复制到世界 data 文件夹。
如果 setup 没生成展示框，检查坐标附近是否被方块或实体占用。
"""

def generate_datapack(
    world_data_dir: Path,
    datapack_dir: Path,
    namespace: str,
    start_map: int,
    x: int,
    y: int,
    z: int,
    frame_delay: int,
    use_glow_frame: bool,
    overwrite: bool,
    meta_dir: Path | None = None,
):
    all_ids = scan_map_ids(world_data_dir)

    if not all_ids:
        raise RuntimeError(f"没有在 {world_data_dir} 里找到任何 map_*.dat")

    continuous_ids = get_continuous_map_ids(all_ids, start_map)

    if not continuous_ids:
        raise RuntimeError(
            f"没有找到从 map_{start_map}.dat 开始的连续地图文件。"
        )

    frame_count = len(continuous_ids)
    end_map = continuous_ids[-1]

    unused_ids = [map_id for map_id in all_ids if map_id > end_map]

    if datapack_dir.exists():
        if overwrite:
            shutil.rmtree(datapack_dir)
        else:
            raise FileExistsError(
                f"输出文件夹已存在：{datapack_dir}\n"
                f"如需覆盖，请重新运行并选择覆盖。"
            )

    datapack_dir.mkdir(parents=True, exist_ok=True)

    generate_pack_mcmeta(
        datapack_dir,
        description=f"{namespace} dynamic map movie datapack"
    )

    generate_function_tags(datapack_dir, namespace)

    generate_basic_functions(
        datapack_dir=datapack_dir,
        namespace=namespace,
        frame_count=frame_count,
        start_map=start_map,
        x=x,
        y=y,
        z=z,
        frame_delay=frame_delay,
        use_glow_frame=use_glow_frame,
    )

    config = {
        "tool": "gif2mc",
        "version": "v0.3-single-frame",
        "minecraft": "Java 1.21+",
        "namespace": namespace,
        "world_data_dir": str(world_data_dir),
        "datapack_dir": str(datapack_dir),
        "start_map": start_map,
        "end_map": end_map,
        "frame_count": frame_count,
        "frame_delay": frame_delay,
        "init_delay": 10,
        "init_f_delay": 4,
        "x": x,
        "y": y,
        "z": z,
        "frame_entity": frame_entity if (frame_entity := ("minecraft:glow_item_frame" if use_glow_frame else "minecraft:item_frame")) else "minecraft:glow_item_frame",
        "commands": [
            "/reload",
            f"/function {namespace}:setup",
            f"/function {namespace}:init",
            f"/function {namespace}:init_f",
            f"/function {namespace}:start",
            f"/function {namespace}:pause",
            f"/function {namespace}:restart",
        ],
    }

    if meta_dir is None:
        meta_dir = datapack_dir.parent
    meta_dir.mkdir(parents=True, exist_ok=True)
    write_text(meta_dir / "config.json", json.dumps(config, ensure_ascii=False, indent=2))
    write_text(meta_dir / "README.txt", make_output_readme(config))

    print()
    print("数据包生成完成。")
    print(f"world_data 文件夹: {world_data_dir}")
    print(f"datapack 文件夹:   {datapack_dir}")
    print(f"namespace:        {namespace}")
    print(f"map 范围:          map_{start_map}.dat ~ map_{end_map}.dat")
    print(f"帧数量:            {frame_count}")
    print(f"坐标:              {x} {y} {z}")
    print(f"frame-delay:       {frame_delay}")
    print("init:              2 FPS")
    print("init_f:            5 FPS")
    print(f"展示框类型:         {'glow_item_frame' if use_glow_frame else 'item_frame'}")

    if unused_ids:
        print()
        print("注意：检测到后面还有 map 文件，但因为中间可能断号，本次不会播放这些：")
        print(", ".join(f"map_{i}.dat" for i in unused_ids[:20]))
        if len(unused_ids) > 20:
            print("...")

    print()
    print("游戏内测试命令：")
    print("/reload")
    print(f"/function {namespace}:setup")
    print(f"/function {namespace}:init")
    print(f"/function {namespace}:init_f")
    print(f"/function {namespace}:start")
    print(f"/function {namespace}:pause")
    print(f"/function {namespace}:restart")


# =========================
# 主程序
# =========================

def main():
    parser = argparse.ArgumentParser(description="Minecraft Java 1.21+ 动态地图数据包生成器")
    parser.add_argument("--world-data", default="out/data", help="map_*.dat 所在文件夹，默认 out/data")
    parser.add_argument("--datapack", default="out/datapack", help="数据包输出文件夹，默认 out/datapack")
    parser.add_argument("--namespace", default="gif2mc", help="数据包命名空间，默认 gif2mc")
    parser.add_argument("--start-map", type=int, default=None, help="起始 map id；默认自动使用最小 map id")
    parser.add_argument("--x", type=int, default=0, help="展示框支撑方块 x，默认 0")
    parser.add_argument("--y", type=int, default=-60, help="展示框支撑方块 y，默认 -60")
    parser.add_argument("--z", type=int, default=0, help="展示框支撑方块 z，默认 0")
    parser.add_argument("--frame-delay", type=int, default=20, help="播放帧间隔 tick，20=1 FPS，2=10 FPS，默认 20")
    parser.add_argument("--use-glow-frame", choices=["true", "false"], default="true", help="是否使用发光展示框，默认 true")
    parser.add_argument("--meta-dir", default="out", help="README.txt 和 config.json 输出位置，默认 out")
    parser.add_argument("--yes", action="store_true", help="非交互模式，直接使用参数")
    args = parser.parse_args()

    print("=== 03_gen_datapack.py ===")
    print("Minecraft Java 1.21+ 动态地图数据包生成器")
    print()

    world_data_dir = Path(args.world_data)
    datapack_dir = Path(args.datapack)

    all_ids = scan_map_ids(world_data_dir)
    if not all_ids:
        print(f"错误：没有在 {world_data_dir} 里找到 map_*.dat")
        return

    detected_start_map = min(all_ids)
    start_map = args.start_map if args.start_map is not None else detected_start_map
    namespace = args.namespace
    x, y, z = args.x, args.y, args.z
    frame_delay = args.frame_delay
    use_glow_frame = args.use_glow_frame.lower() == "true"

    if not args.yes:
        print(f"检测到 map id：{all_ids[0]} ~ {all_ids[-1]}")
        print(f"默认起始 map id：{detected_start_map}")
        print("直接回车使用方括号里的默认值。")
        print()

        world_data_dir = Path(ask("world_data 文件夹", str(world_data_dir)))
        datapack_dir = Path(ask("datapack 输出文件夹", str(datapack_dir)))
        namespace = ask("namespace", namespace)
        start_map = ask_int("起始 map id", start_map)
        x = ask_int("展示框支撑方块 x", x)
        y = ask_int("展示框支撑方块 y", y)
        z = ask_int("展示框支撑方块 z", z)
        frame_delay = ask_int("frame-delay，20=每秒1帧，2=每秒10帧", frame_delay)
        use_glow_frame = ask_yes_no("使用发光展示框", use_glow_frame)

    overwrite = True
    if datapack_dir.exists() and not args.yes:
        overwrite = ask_yes_no(f"{datapack_dir} 已存在，是否覆盖", True)

    generate_datapack(
        world_data_dir=world_data_dir,
        datapack_dir=datapack_dir,
        namespace=namespace,
        start_map=start_map,
        x=x,
        y=y,
        z=z,
        frame_delay=frame_delay,
        use_glow_frame=use_glow_frame,
        overwrite=overwrite,
        meta_dir=Path(args.meta_dir),
    )


if __name__ == "__main__":
    main()
