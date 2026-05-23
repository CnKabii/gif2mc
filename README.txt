Gif2Mc v0.3 单展示框动态地图工具

当前功能
1. 把 mp4/gif 切成 128x128 PNG 图片序列。
2. 把图片序列转换为 Minecraft Java 地图数据 map_*.dat / idcounts.dat。
3. 自动生成 Minecraft Java 1.21+ 数据包，实现游戏内 setup / init / init_f / start / pause / restart。

推荐文件结构
00_run_all.py        一键流程入口，可选使用
01_split_video.py    视频/GIF -> in/frame_*.png
02_gen_map_dat.py    in/frame_*.png -> out/data/map_*.dat
03_gen_datapack.py   out/data/map_*.dat -> out/datapack
README.txt           本说明

依赖
1. Python 3.8+
2. Pillow：pip install pillow
3. ffmpeg：用于视频/GIF 切帧，并确保 ffmpeg 在 PATH 中

一键流程
从视频开始：
python 00_run_all.py

或者非交互：
python 00_run_all.py --video video.mp4 --fps 10 --start-map 0 --x 0 --y -60 --z 0 --namespace gif2mc --frame-delay 2 --yes

如果已经有 in/frame_*.png：
python 00_run_all.py --skip-split --frames in --start-map 0 --x 0 --y -60 --z 0 --namespace gif2mc --frame-delay 2 --yes

分步流程
1. 切帧：
python 01_split_video.py

2. 生成地图数据：
python 02_gen_map_dat.py

3. 生成数据包：
python 03_gen_datapack.py

默认输出
out/data/       map_*.dat 和 idcounts.dat
out/datapack/   Minecraft 数据包
out/README.txt  本次生成结果说明
out/config.json 本次生成参数记录

放入世界
1. 把 out/data/ 里的 map_*.dat 和 idcounts.dat 复制到世界存档的 data 文件夹。
2. 把 out/datapack/ 复制到世界存档的 datapacks 文件夹，并确保 pack.mcmeta 直接在数据包根目录。

游戏内命令
/reload
/function gif2mc:setup
/function gif2mc:init
/function gif2mc:init_f
/function gif2mc:start
/function gif2mc:pause
/function gif2mc:restart

命令说明
setup   创建屏幕并显示第一帧
init    2 FPS 慢速预载一遍，完成后回到第一帧并暂停
init_f  5 FPS 快速预载一遍，完成后回到第一帧并暂停
start   开始正常播放
pause   暂停播放
restart 从第一帧重新开始正常播放

当前版本建议
v0.3 先保持单展示框稳定，不急着加大屏幕。多展示框大屏幕会同时影响地图切片和数据包播放逻辑，建议作为 v0.4/v0.5 单独设计。
