package com.gif2mc;

import com.mojang.brigadier.Command;
import com.mojang.brigadier.arguments.IntegerArgumentType;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.context.CommandContext;
import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.command.v2.CommandRegistrationCallback;
import net.minecraft.block.Blocks;
import net.minecraft.block.MapColor;
import net.minecraft.component.DataComponentTypes;
import net.minecraft.component.type.MapIdComponent;
import net.minecraft.entity.decoration.GlowItemFrameEntity;
import net.minecraft.entity.decoration.ItemFrameEntity;
import net.minecraft.item.ItemStack;
import net.minecraft.item.Items;
import net.minecraft.item.map.MapState;
import net.minecraft.network.packet.Packet;
import net.minecraft.server.command.CommandManager;
import net.minecraft.server.command.ServerCommandSource;
import net.minecraft.server.network.ServerPlayerEntity;
import net.minecraft.server.world.ServerWorld;
import net.minecraft.text.Text;
import net.minecraft.util.math.BlockPos;
import net.minecraft.util.math.Box;
import net.minecraft.util.math.Direction;
import net.minecraft.util.math.Vec3d;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.minecraft.registry.RegistryKey;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.World;


import java.util.Comparator;
import java.util.stream.Stream;
import javax.imageio.ImageIO;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

public class Gif2McMod implements ModInitializer {
    public static final String MOD_ID = "gif2mc";

    private static final String TAG_SCREEN = "gif2mc_screen";
    private static final String TAG_TILE = "gif2mc_tile";
    private static final String TAG_FACING_PREFIX = "gif2mc_facing_";

    private static final BlockPos DEFAULT_ORIGIN = new BlockPos(0, -60, 0);
    private static final Direction DEFAULT_FACING = Direction.SOUTH;

    private static final int MAP_SIZE = 128;
    private static final String INPUT_DIR = "gif2mc";

    /*
     * 流式缓存帧数。
     * 2x2 时约 2.5MB，4x4 时约 10MB。
     * 比全量缓存稳定得多。
     */
    private static final int STREAM_CACHE_FRAMES = 40;

    private static final List<PaletteEntry> MAP_PALETTE = buildMapPalette();

    /*
     * 15-bit RGB 查表：
     * 把 256^3 色彩空间压到 32^3 = 32768 个桶。
     * 预先算出每个桶最接近的 Minecraft 地图颜色。
     */
    private static final byte[] RGB_15BIT_LOOKUP = buildRgb15BitLookup();

    private static volatile PlaybackState playbackState = null;

    @Override
    public void onInitialize() {
        System.out.println("[gif2mc] Gif2MC Fabric MVP initialized.");

        CommandRegistrationCallback.EVENT.register((dispatcher, registryAccess, environment) -> {
            dispatcher.register(
                    CommandManager.literal("gif2mc")
                            .executes(Gif2McMod::executeRoot)

                            .then(CommandManager.literal("ping")
                                    .executes(context -> {
                                        send(context, "pong");
                                        return Command.SINGLE_SUCCESS;
                                    })
                            )

                            .then(CommandManager.literal("help")
                                    .executes(Gif2McMod::executeHelp)
                            )

                            .then(CommandManager.literal("info")
                                    .executes(Gif2McMod::executeInfo)
                            )

                            .then(CommandManager.literal("setup")
                                    .executes(context -> executeSetup(
                                            context,
                                            1,
                                            1,
                                            0,
                                            DEFAULT_ORIGIN,
                                            DEFAULT_FACING
                                    ))

                                    .then(CommandManager.argument("width", IntegerArgumentType.integer(1, 32))
                                            .then(CommandManager.argument("height", IntegerArgumentType.integer(1, 32))
                                                    .then(CommandManager.argument("startMapId", IntegerArgumentType.integer(0))
                                                            .executes(context -> executeSetup(
                                                                    context,
                                                                    IntegerArgumentType.getInteger(context, "width"),
                                                                    IntegerArgumentType.getInteger(context, "height"),
                                                                    IntegerArgumentType.getInteger(context, "startMapId"),
                                                                    DEFAULT_ORIGIN,
                                                                    DEFAULT_FACING
                                                            ))
                                                    )
                                            )
                                    )
                            )

                            .then(CommandManager.literal("setupAt")
                                    .then(CommandManager.argument("width", IntegerArgumentType.integer(1, 32))
                                            .then(CommandManager.argument("height", IntegerArgumentType.integer(1, 32))
                                                    .then(CommandManager.argument("startMapId", IntegerArgumentType.integer(0))
                                                            .then(CommandManager.argument("x", IntegerArgumentType.integer())
                                                                    .then(CommandManager.argument("y", IntegerArgumentType.integer())
                                                                            .then(CommandManager.argument("z", IntegerArgumentType.integer())
                                                                                    .then(CommandManager.argument("facing", StringArgumentType.word())
                                                                                            .executes(context -> {
                                                                                                int width = IntegerArgumentType.getInteger(context, "width");
                                                                                                int height = IntegerArgumentType.getInteger(context, "height");
                                                                                                int startMapId = IntegerArgumentType.getInteger(context, "startMapId");
                                                                                                int x = IntegerArgumentType.getInteger(context, "x");
                                                                                                int y = IntegerArgumentType.getInteger(context, "y");
                                                                                                int z = IntegerArgumentType.getInteger(context, "z");

                                                                                                Direction facing = parseFacing(StringArgumentType.getString(context, "facing"));
                                                                                                if (facing == null) {
                                                                                                    context.getSource().sendError(Text.literal(
                                                                                                            "facing 只能是 north / south / east / west"
                                                                                                    ));
                                                                                                    return 0;
                                                                                                }

                                                                                                return executeSetup(
                                                                                                        context,
                                                                                                        width,
                                                                                                        height,
                                                                                                        startMapId,
                                                                                                        new BlockPos(x, y, z),
                                                                                                        facing
                                                                                                );
                                                                                            })
                                                                                    )
                                                                            )
                                                                    )
                                                            )
                                                    )
                                            )
                                    )
                            )

                            .then(CommandManager.literal("loadPng")
                                    .then(CommandManager.argument("mapId", IntegerArgumentType.integer(0))
                                            .then(CommandManager.argument("filename", StringArgumentType.greedyString())
                                                    .executes(Gif2McMod::executeLoadPng)
                                            )
                                    )
                            )

                            .then(CommandManager.literal("loadGrid")
                                    .then(CommandManager.argument("startMapId", IntegerArgumentType.integer(0))
                                            .then(CommandManager.argument("width", IntegerArgumentType.integer(1, 32))
                                                    .then(CommandManager.argument("height", IntegerArgumentType.integer(1, 32))
                                                            .then(CommandManager.argument("filename", StringArgumentType.greedyString())
                                                                    .executes(Gif2McMod::executeLoadGrid)
                                                            )
                                                    )
                                            )
                                    )
                            )

                            .then(CommandManager.literal("play")
                                    .then(CommandManager.argument("startMapId", IntegerArgumentType.integer(0))
                                            .then(CommandManager.argument("width", IntegerArgumentType.integer(1, 32))
                                                    .then(CommandManager.argument("height", IntegerArgumentType.integer(1, 32))
                                                            .then(CommandManager.argument("folder", StringArgumentType.word())
                                                                    .then(CommandManager.argument("fps", IntegerArgumentType.integer(1, 20))
                                                                            .executes(context -> executePlay(context, true))
                                                                    )
                                                            )
                                                    )
                                            )
                                    )
                            )

                            .then(CommandManager.literal("playOnce")
                                    .then(CommandManager.argument("startMapId", IntegerArgumentType.integer(0))
                                            .then(CommandManager.argument("width", IntegerArgumentType.integer(1, 32))
                                                    .then(CommandManager.argument("height", IntegerArgumentType.integer(1, 32))
                                                            .then(CommandManager.argument("folder", StringArgumentType.word())
                                                                    .then(CommandManager.argument("fps", IntegerArgumentType.integer(1, 20))
                                                                            .executes(context -> executePlay(context, false))
                                                                    )
                                                            )
                                                    )
                                            )
                                    )
                            )

                            .then(CommandManager.literal("stop")
                                    .executes(Gif2McMod::executeStop)
                            )

                            .then(CommandManager.literal("status")
                                    .executes(Gif2McMod::executeStatus)
                            )

                            .then(CommandManager.literal("clear")
                                    .executes(context -> executeClear(context, 64))

                                    .then(CommandManager.argument("radius", IntegerArgumentType.integer(1, 512))
                                            .executes(context -> executeClear(
                                                    context,
                                                    IntegerArgumentType.getInteger(context, "radius")
                                            ))
                                    )
                            )
            );
        });

        ServerTickEvents.END_SERVER_TICK.register(Gif2McMod::onEndServerTick);
    }

    private static int executeRoot(CommandContext<ServerCommandSource> context) {
        send(context, "Gif2MC 已加载。试试 /gif2mc help");
        return Command.SINGLE_SUCCESS;
    }

    private static int executeHelp(CommandContext<ServerCommandSource> context) {
        send(context, "Gif2MC commands:");
        send(context, "/gif2mc setup");
        send(context, "/gif2mc setup <width> <height> <startMapId>");
        send(context, "/gif2mc setupAt <width> <height> <startMapId> <x> <y> <z> <north|south|east|west>");
        send(context, "/gif2mc loadPng <mapId> <filename>");
        send(context, "/gif2mc loadGrid <startMapId> <width> <height> <filename>");
        send(context, "/gif2mc play <startMapId> <width> <height> <folder> <fps>");
        send(context, "/gif2mc playOnce <startMapId> <width> <height> <folder> <fps>");
        send(context, "/gif2mc stop");
        send(context, "/gif2mc status");
        send(context, "/gif2mc clear");
        send(context, "/gif2mc clear <radius>");
        send(context, "例子：/gif2mc setupAt 2 2 0 0 -60 0 south");
        send(context, "例子：/gif2mc loadPng 0 test.png");
        send(context, "例子：/gif2mc play 0 2 2 frames 10");
        send(context, "PNG 文件目录：" + INPUT_DIR + "/");
        return Command.SINGLE_SUCCESS;
    }

    private static int executeInfo(CommandContext<ServerCommandSource> context) {
        ServerCommandSource source = context.getSource();
        ServerWorld world = source.getWorld();
        Vec3d pos = source.getPosition();
        Path inputDir = source.getServer().getPath(INPUT_DIR);

        send(context, "Gif2MC Fabric MVP v0.4");
        send(context, "当前维度：" + world.getRegistryKey().getValue());
        send(context, "当前位置：" + formatPos(pos));
        send(context, "默认屏幕原点：0 -60 0，默认朝向：south");
        send(context, "PNG 输入目录：" + inputDir.toAbsolutePath());
        send(context, "地图调色板颜色数：" + MAP_PALETTE.size());
        return Command.SINGLE_SUCCESS;
    }

    private static int executeSetup(
            CommandContext<ServerCommandSource> context,
            int width,
            int height,
            int startMapId,
            BlockPos origin,
            Direction facing
    ) {
        if (width * height > 1024) {
            context.getSource().sendError(Text.literal("一次最多生成 1024 个 tile，先别太猛。"));
            return 0;
        }

        ServerWorld world = context.getSource().getWorld();

        Box cleanupBox = makeScreenBox(origin, width, height, facing).expand(4.0);
        ClearResult clearResult = clearTaggedFramesAndBarriers(world, cleanupBox);

        int spawned = 0;
        int barriersPlaced = 0;

        for (int row = 0; row < height; row++) {
            for (int col = 0; col < width; col++) {
                int mapId = startMapId + row * width + col;

                BlockPos framePos = getTileFrameBlockPos(origin, col, row, facing);
                BlockPos barrierPos = getBackingBlockPos(framePos, facing);

                world.setBlockState(barrierPos, Blocks.BARRIER.getDefaultState());
                barriersPlaced++;

                GlowItemFrameEntity frame = new GlowItemFrameEntity(world, framePos, facing);
                frame.addCommandTag(TAG_SCREEN);
                frame.addCommandTag(TAG_TILE);
                frame.addCommandTag(TAG_FACING_PREFIX + facing.asString());
                frame.addCommandTag("gif2mc_map_" + mapId);
                frame.addCommandTag("gif2mc_col_" + col);
                frame.addCommandTag("gif2mc_row_" + row);
                frame.setInvulnerable(true);
                frame.setRotation(0);

                ItemStack mapStack = createFilledMapStack(mapId);
                frame.setHeldItemStack(mapStack, false);

                boolean ok = world.spawnEntity(frame);
                if (ok) {
                    spawned++;
                }
            }
        }

        send(context, "已生成 Gif2MC 屏幕。");
        send(context, "尺寸：" + width + "x" + height);
        send(context, "展示框原点：" + origin.getX() + " " + origin.getY() + " " + origin.getZ());
        send(context, "朝向：" + facing.asString());
        send(context, "屏障位置：展示框背后 " + facing.getOpposite().asString() + " 方向一格");
        send(context, "地图 ID：" + startMapId + " 到 " + (startMapId + width * height - 1));
        send(context, "清理旧展示框：" + clearResult.frames() + " 个；清理旧屏障：" + clearResult.barriers() + " 个。");
        send(context, "新生成展示框：" + spawned + " 个；新放置屏障：" + barriersPlaced + " 个。");

        return spawned;
    }

    private static int executeLoadPng(CommandContext<ServerCommandSource> context) {
        ServerCommandSource source = context.getSource();
        ServerWorld world = source.getWorld();

        int rawMapId = IntegerArgumentType.getInteger(context, "mapId");
        String filename = StringArgumentType.getString(context, "filename").trim();

        if (filename.isEmpty()) {
            source.sendError(Text.literal("文件名不能为空。"));
            return 0;
        }

        try {
            Path inputDir = source.getServer().getPath(INPUT_DIR).normalize();
            Files.createDirectories(inputDir);

            Path imagePath = inputDir.resolve(filename).normalize();

            if (!imagePath.startsWith(inputDir)) {
                source.sendError(Text.literal("文件路径不允许跳出 " + INPUT_DIR + " 目录。"));
                return 0;
            }

            if (!Files.exists(imagePath)) {
                source.sendError(Text.literal("找不到 PNG 文件：" + imagePath.toAbsolutePath()));
                send(context, "请把图片放到：" + inputDir.toAbsolutePath());
                return 0;
            }

            BufferedImage image = ImageIO.read(imagePath.toFile());
            if (image == null) {
                source.sendError(Text.literal("读取失败：这看起来不是有效图片文件。"));
                return 0;
            }

            boolean resized = image.getWidth() != MAP_SIZE || image.getHeight() != MAP_SIZE;
            BufferedImage normalizedImage = normalizeImageToMapSize(image);

            MapIdComponent mapId = new MapIdComponent(rawMapId);
            MapState state = getOrCreateMapState(world, mapId);

            int changedPixels = writeImageToMapState(state, normalizedImage);
            state.markDirty();

            forceSendMapUpdate(world, mapId, state);

            send(context, "PNG 已写入地图。");
            send(context, "文件：" + imagePath.getFileName());
            send(context, "map_id：" + rawMapId);
            send(context, "原始尺寸：" + image.getWidth() + "x" + image.getHeight());
            send(context, "写入尺寸：128x128");
            send(context, "变化像素：" + changedPixels + " / 16384");
            if (resized) {
                send(context, "注意：图片不是 128x128，已自动缩放。正式视频帧建议提前处理成 128x128。");
            }

            return Command.SINGLE_SUCCESS;
        } catch (IOException e) {
            source.sendError(Text.literal("读取 PNG 出错：" + e.getMessage()));
            return 0;
        } catch (Exception e) {
            source.sendError(Text.literal("loadPng 执行失败：" + e.getClass().getSimpleName() + ": " + e.getMessage()));
            e.printStackTrace();
            return 0;
        }
    }

    private static int executeLoadGrid(CommandContext<ServerCommandSource> context) {
        ServerCommandSource source = context.getSource();
        ServerWorld world = source.getWorld();

        int startMapId = IntegerArgumentType.getInteger(context, "startMapId");
        int width = IntegerArgumentType.getInteger(context, "width");
        int height = IntegerArgumentType.getInteger(context, "height");
        String filename = StringArgumentType.getString(context, "filename").trim();

        if (filename.isEmpty()) {
            source.sendError(Text.literal("文件名不能为空。"));
            return 0;
        }

        int mapCount = width * height;

        if (mapCount > 1024) {
            source.sendError(Text.literal("一次最多写入 1024 张地图，先别太猛。"));
            return 0;
        }

        try {
            Path inputDir = source.getServer().getPath(INPUT_DIR).normalize();
            Files.createDirectories(inputDir);

            Path imagePath = inputDir.resolve(filename).normalize();

            if (!imagePath.startsWith(inputDir)) {
                source.sendError(Text.literal("文件路径不允许跳出 " + INPUT_DIR + " 目录。"));
                return 0;
            }

            if (!Files.exists(imagePath)) {
                source.sendError(Text.literal("找不到图片文件：" + imagePath.toAbsolutePath()));
                send(context, "请把图片放到：" + inputDir.toAbsolutePath());
                return 0;
            }

            GridWriteResult result = loadGridImageIntoMaps(world, imagePath, startMapId, width, height);

            send(context, "大图已切片并写入地图。");
            send(context, "文件：" + imagePath.getFileName());
            send(context, "网格：" + width + "x" + height + "，共 " + mapCount + " 张地图。");
            send(context, "map_id：" + startMapId + " 到 " + (startMapId + mapCount - 1));
            send(context, "原始尺寸：" + result.originalWidth() + "x" + result.originalHeight());
            send(context, "写入尺寸：" + result.targetWidth() + "x" + result.targetHeight());
            send(context, "变化像素：" + result.changedPixels() + " / " + (mapCount * MAP_SIZE * MAP_SIZE));

            if (result.resized()) {
                send(context, "注意：图片尺寸不是 " + result.targetWidth() + "x" + result.targetHeight() + "，已自动缩放。");
                send(context, "正式视频帧建议提前处理成目标尺寸，避免实时缩放影响效果。");
            }

            return mapCount;
        } catch (IOException e) {
            source.sendError(Text.literal("读取图片出错：" + e.getMessage()));
            return 0;
        } catch (Exception e) {
            source.sendError(Text.literal("loadGrid 执行失败：" + e.getClass().getSimpleName() + ": " + e.getMessage()));
            e.printStackTrace();
            return 0;
        }
    }

    private static int executePlay(CommandContext<ServerCommandSource> context, boolean loop) {
        ServerCommandSource source = context.getSource();
        ServerWorld world = source.getWorld();

        int startMapId = IntegerArgumentType.getInteger(context, "startMapId");
        int width = IntegerArgumentType.getInteger(context, "width");
        int height = IntegerArgumentType.getInteger(context, "height");
        String folder = StringArgumentType.getString(context, "folder").trim();
        int fps = IntegerArgumentType.getInteger(context, "fps");

        int mapCount = width * height;

        if (mapCount > 1024) {
            source.sendError(Text.literal("一次最多播放 1024 张地图组成的屏幕，先别太猛。"));
            return 0;
        }

        try {
            Path inputDir = source.getServer().getPath(INPUT_DIR).normalize();
            Files.createDirectories(inputDir);

            Path frameDir = inputDir.resolve(folder).normalize();

            if (!frameDir.startsWith(inputDir)) {
                source.sendError(Text.literal("帧目录不允许跳出 " + INPUT_DIR + " 目录。"));
                return 0;
            }

            if (!Files.isDirectory(frameDir)) {
                source.sendError(Text.literal("找不到帧目录：" + frameDir.toAbsolutePath()));
                send(context, "请把帧目录放到：" + inputDir.toAbsolutePath());
                return 0;
            }

            List<Path> frameFiles = scanFrameFiles(frameDir);

            if (frameFiles.isEmpty()) {
                source.sendError(Text.literal("帧目录里没有 PNG 文件：" + frameDir.toAbsolutePath()));
                return 0;
            }

            PlaybackState old = playbackState;
            if (old != null) {
                stopPlaybackState(old);
            }

            PlaybackState state = new PlaybackState(
                    world.getRegistryKey(),
                    startMapId,
                    width,
                    height,
                    frameDir,
                    frameFiles,
                    fps,
                    loop
            );

            playbackState = state;
            state.tickAccumulator = 20;

            startFrameLoader(state);

            int effectiveCacheFrames = Math.min(STREAM_CACHE_FRAMES, frameFiles.size());
            long estimatedCacheBytes = estimateCachedBytes(effectiveCacheFrames, width, height);

            send(context, "Gif2MC 播放已启动。");
            send(context, "模式：" + (loop ? "循环播放" : "播放一遍"));
            send(context, "播放方式：流式小缓存");
            send(context, "目录：" + frameDir.toAbsolutePath());
            send(context, "帧数：" + frameFiles.size());
            send(context, "缓存帧数：" + STREAM_CACHE_FRAMES + "，预计缓存占用：" + formatBytes(estimatedCacheBytes));
            send(context, "网格：" + width + "x" + height + "，map_id " + startMapId + " 到 " + (startMapId + mapCount - 1));
            send(context, "FPS：" + fps);
            send(context, "第一帧：" + frameFiles.get(0).getFileName());

            return Command.SINGLE_SUCCESS;
        } catch (IOException e) {
            source.sendError(Text.literal("扫描帧目录失败：" + e.getMessage()));
            return 0;
        } catch (Exception e) {
            source.sendError(Text.literal("play 执行失败：" + e.getClass().getSimpleName() + ": " + e.getMessage()));
            e.printStackTrace();
            return 0;
        }
    }

    private static List<Path> scanFrameFiles(Path frameDir) throws IOException {
        try (Stream<Path> stream = Files.list(frameDir)) {
            return stream
                    .filter(Files::isRegularFile)
                    .filter(Gif2McMod::isPngFile)
                    .sorted(Comparator.comparing(path -> path.getFileName().toString()))
                    .toList();
        }
    }

    private static void startFrameLoader(PlaybackState state) {
        Thread thread = new Thread(() -> {
            try {
                do {
                    for (Path frameFile : state.frameFiles) {
                        if (state.stopRequested) {
                            return;
                        }

                        CachedFrame frame = loadCachedFrame(
                                frameFile,
                                state.width,
                                state.height
                        );

                        while (!state.stopRequested) {
                            if (state.frameQueue.offer(frame, 100, TimeUnit.MILLISECONDS)) {
                                state.decodedFrames++;
                                break;
                            }
                        }
                    }
                } while (state.loop && !state.stopRequested);

                state.loaderDone = true;
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                state.loaderDone = true;
            } catch (Exception e) {
                state.loaderError = e.getClass().getSimpleName() + ": " + e.getMessage();
                state.loaderDone = true;
                e.printStackTrace();
            }
        }, "gif2mc-frame-loader");

        thread.setDaemon(true);
        state.loaderThread = thread;
        thread.start();
    }

    private static void stopPlaybackState(PlaybackState state) {
        state.stopRequested = true;

        Thread thread = state.loaderThread;
        if (thread != null) {
            thread.interrupt();
        }

        state.frameQueue.clear();
    }

    private static long estimateCachedBytes(int frameCount, int width, int height) {
        return (long) frameCount * width * height * MAP_SIZE * MAP_SIZE;
    }

    private static String formatBytes(long bytes) {
        double mb = bytes / 1024.0 / 1024.0;

        if (mb < 1024.0) {
            return String.format(Locale.ROOT, "%.1f MB", mb);
        }

        double gb = mb / 1024.0;
        return String.format(Locale.ROOT, "%.2f GB", gb);
    }

    private static List<CachedFrame> preloadCachedFrames(
            List<Path> frameFiles,
            int width,
            int height
    ) throws IOException {
        List<CachedFrame> result = new ArrayList<>(frameFiles.size());

        for (Path frameFile : frameFiles) {
            result.add(loadCachedFrame(frameFile, width, height));
        }

        return List.copyOf(result);
    }

    private static CachedFrame loadCachedFrame(
            Path imagePath,
            int width,
            int height
    ) throws IOException {
        BufferedImage image = ImageIO.read(imagePath.toFile());

        if (image == null) {
            throw new IOException("这看起来不是有效图片文件：" + imagePath.getFileName());
        }

        int targetWidth = width * MAP_SIZE;
        int targetHeight = height * MAP_SIZE;

        boolean resized = image.getWidth() != targetWidth || image.getHeight() != targetHeight;
        BufferedImage normalizedImage = normalizeImageToSize(image, targetWidth, targetHeight);

        byte[][] tiles = new byte[width * height][];

        for (int row = 0; row < height; row++) {
            for (int col = 0; col < width; col++) {
                int tileIndex = row * width + col;

                tiles[tileIndex] = imageTileToMapBytes(
                        normalizedImage,
                        col * MAP_SIZE,
                        row * MAP_SIZE
                );
            }
        }

        return new CachedFrame(
                imagePath.getFileName().toString(),
                tiles,
                resized,
                image.getWidth(),
                image.getHeight(),
                targetWidth,
                targetHeight
        );
    }

    private static byte[] imageTileToMapBytes(
            BufferedImage image,
            int offsetX,
            int offsetY
    ) {
        byte[] colors = new byte[MAP_SIZE * MAP_SIZE];

        for (int z = 0; z < MAP_SIZE; z++) {
            for (int x = 0; x < MAP_SIZE; x++) {
                int argb = image.getRGB(offsetX + x, offsetY + z);
                colors[z * MAP_SIZE + x] = closestMapColor(argb);
            }
        }

        return colors;
    }

    private static int writeCachedFrameIntoMaps(
            ServerWorld world,
            CachedFrame frame,
            int startMapId,
            int width,
            int height
    ) {
        int totalChangedPixels = 0;

        for (int row = 0; row < height; row++) {
            for (int col = 0; col < width; col++) {
                int tileIndex = row * width + col;
                int mapIdValue = startMapId + tileIndex;

                MapIdComponent mapId = new MapIdComponent(mapIdValue);
                MapState state = getOrCreateMapState(world, mapId);

                totalChangedPixels += writeMapBytesToMapState(
                        state,
                        frame.tiles()[tileIndex]
                );

                state.markDirty();
                forceSendMapUpdate(world, mapId, state);
            }
        }

        return totalChangedPixels;
    }

    private static int writeMapBytesToMapState(
            MapState state,
            byte[] colors
    ) {
        int changed = 0;

        for (int z = 0; z < MAP_SIZE; z++) {
            int rowOffset = z * MAP_SIZE;

            for (int x = 0; x < MAP_SIZE; x++) {
                byte mapColor = colors[rowOffset + x];

                if (state.putColor(x, z, mapColor)) {
                    changed++;
                }
            }
        }

        return changed;
    }

    private static boolean isPngFile(Path path) {
        String name = path.getFileName().toString().toLowerCase(Locale.ROOT);
        return name.endsWith(".png");
    }

    private static GridWriteResult loadGridImageIntoMaps(
            ServerWorld world,
            Path imagePath,
            int startMapId,
            int width,
            int height
    ) throws IOException {
        CachedFrame frame = loadCachedFrame(imagePath, width, height);

        int totalChangedPixels = writeCachedFrameIntoMaps(
                world,
                frame,
                startMapId,
                width,
                height
        );

        return new GridWriteResult(
                totalChangedPixels,
                frame.resized(),
                frame.originalWidth(),
                frame.originalHeight(),
                frame.targetWidth(),
                frame.targetHeight()
        );
    }

    private static int executeStop(CommandContext<ServerCommandSource> context) {
        PlaybackState old = playbackState;

        if (old == null) {
            send(context, "当前没有正在播放的 Gif2MC 视频。");
            return 0;
        }

        playbackState = null;
        stopPlaybackState(old);

        send(context, "Gif2MC 播放已停止。");
        send(context, "已播放帧数：" + old.playedFrames);
        send(context, "已解码帧数：" + old.decodedFrames);
        if (old.lastFrameName != null) {
            send(context, "最后一帧：" + old.lastFrameName);
        }

        return Command.SINGLE_SUCCESS;
    }

    private static int executeStatus(CommandContext<ServerCommandSource> context) {
        PlaybackState state = playbackState;

        if (state == null) {
            send(context, "当前没有正在播放的 Gif2MC 视频。");
            return Command.SINGLE_SUCCESS;
        }

        send(context, "Gif2MC 正在播放。");
        send(context, "模式：" + (state.loop ? "循环播放" : "播放一遍"));
        send(context, "播放方式：流式小缓存");
        send(context, "目录：" + state.frameDir.toAbsolutePath());
        send(context, "网格：" + state.width + "x" + state.height);
        send(context, "map_id：" + state.startMapId + " 到 " + (state.startMapId + state.width * state.height - 1));
        send(context, "FPS：" + state.fps);
        send(context, "总帧数：" + state.frameFiles.size());
        send(context, "已播放：" + state.playedFrames + "，已解码：" + state.decodedFrames);
        send(context, "队列缓存：" + state.frameQueue.size() + " / " + STREAM_CACHE_FRAMES);
        send(context, "缓存占用约：" + formatBytes(estimateCachedBytes(state.frameQueue.size(), state.width, state.height)));

        if (state.lastFrameName != null) {
            send(context, "最后写入：" + state.lastFrameName);
            send(context, "最后变化像素：" + state.lastChangedPixels);
        }

        if (state.loaderError != null) {
            send(context, "解码线程错误：" + state.loaderError);
        }

        if (state.lastError != null) {
            send(context, "播放写入错误：" + state.lastError);
        }

        return Command.SINGLE_SUCCESS;
    }

    private static void onEndServerTick(MinecraftServer server) {
        PlaybackState state = playbackState;

        if (state == null) {
            return;
        }

        if (state.loaderError != null) {
            System.out.println("[gif2mc] Playback stopped because frame loader failed: " + state.loaderError);
            playbackState = null;
            stopPlaybackState(state);
            return;
        }

        state.tickAccumulator += state.fps;

        if (state.tickAccumulator < 20) {
            return;
        }

        state.tickAccumulator -= 20;

        ServerWorld world = server.getWorld(state.worldKey);

        if (world == null) {
            System.out.println("[gif2mc] Playback stopped: target world is not loaded.");
            playbackState = null;
            stopPlaybackState(state);
            return;
        }

        CachedFrame frame = state.frameQueue.poll();

        if (frame == null) {
            /*
             * 队列暂时没帧，说明解码跟不上。
             * 这里选择“等一等”，不重复上一帧，不强行跳帧。
             */
            if (state.loaderDone && !state.loop) {
                System.out.println("[gif2mc] Playback finished.");
                playbackState = null;
                stopPlaybackState(state);
            }
            return;
        }

        try {
            int changedPixels = writeCachedFrameIntoMaps(
                    world,
                    frame,
                    state.startMapId,
                    state.width,
                    state.height
            );

            state.lastFrameName = frame.name();
            state.lastChangedPixels = changedPixels;
            state.lastError = null;
            state.playedFrames++;
        } catch (Exception e) {
            state.lastError = e.getClass().getSimpleName() + ": " + e.getMessage();
            System.out.println("[gif2mc] Playback stopped because cached frame writing failed: " + state.lastError);
            e.printStackTrace();

            playbackState = null;
            stopPlaybackState(state);
        }
    }

    private static int executeClear(CommandContext<ServerCommandSource> context, int radius) {
        ServerCommandSource source = context.getSource();
        ServerWorld world = source.getWorld();
        Vec3d pos = source.getPosition();

        Box box = new Box(
                pos.x - radius,
                pos.y - radius,
                pos.z - radius,
                pos.x + radius,
                pos.y + radius,
                pos.z + radius
        );

        ClearResult result = clearTaggedFramesAndBarriers(world, box);

        send(context, "已清理附近 " + radius + " 格内的 Gif2MC 内容。");
        send(context, "展示框：" + result.frames() + " 个。");
        send(context, "屏障：" + result.barriers() + " 个。");

        return result.frames() + result.barriers();
    }

    private static ClearResult clearTaggedFramesAndBarriers(ServerWorld world, Box box) {
        List<ItemFrameEntity> frames = world.getEntitiesByClass(
                ItemFrameEntity.class,
                box,
                frame -> frame.getCommandTags().contains(TAG_SCREEN)
        );

        int clearedBarriers = 0;

        for (ItemFrameEntity frame : frames) {
            clearedBarriers += clearBarrierForFrame(world, frame);
            frame.discard();
        }

        return new ClearResult(frames.size(), clearedBarriers);
    }

    private static int clearBarrierForFrame(ServerWorld world, ItemFrameEntity frame) {
        int cleared = 0;

        BlockPos framePos = frame.getBlockPos();

        if (world.getBlockState(framePos).isOf(Blocks.BARRIER)) {
            world.setBlockState(framePos, Blocks.AIR.getDefaultState());
            cleared++;
        }

        Direction facing = getFacingFromFrameTags(frame);
        if (facing != null) {
            BlockPos backingPos = getBackingBlockPos(framePos, facing);

            if (!backingPos.equals(framePos) && world.getBlockState(backingPos).isOf(Blocks.BARRIER)) {
                world.setBlockState(backingPos, Blocks.AIR.getDefaultState());
                cleared++;
            }
        }

        return cleared;
    }

    private static Direction getFacingFromFrameTags(ItemFrameEntity frame) {
        Set<String> tags = frame.getCommandTags();

        for (String tag : tags) {
            if (tag.startsWith(TAG_FACING_PREFIX)) {
                String rawFacing = tag.substring(TAG_FACING_PREFIX.length());
                Direction facing = parseFacing(rawFacing);
                if (facing != null) {
                    return facing;
                }
            }
        }

        return null;
    }

    private static ItemStack createFilledMapStack(int mapId) {
        ItemStack stack = new ItemStack(Items.FILLED_MAP);
        stack.set(DataComponentTypes.MAP_ID, new MapIdComponent(mapId));
        return stack;
    }

    private static MapState getOrCreateMapState(ServerWorld world, MapIdComponent mapId) {
        MapState state = world.getMapState(mapId);

        if (state == null) {
            state = MapState.of(
                    0.0,
                    0.0,
                    (byte) 0,
                    false,
                    false,
                    world.getRegistryKey()
            );
            world.putMapState(mapId, state);
        }

        return state;
    }

    private static int writeImageToMapState(MapState state, BufferedImage image) {
        int changed = 0;

        for (int z = 0; z < MAP_SIZE; z++) {
            for (int x = 0; x < MAP_SIZE; x++) {
                int argb = image.getRGB(x, z);
                byte mapColor = closestMapColor(argb);

                if (state.putColor(x, z, mapColor)) {
                    changed++;
                }
            }
        }

        return changed;
    }

    private static void forceSendMapUpdate(ServerWorld world, MapIdComponent mapId, MapState state) {
        for (ServerPlayerEntity player : world.getPlayers()) {
            Packet<?> packet = state.getPlayerMarkerPacket(mapId, player);
            if (packet != null) {
                player.networkHandler.sendPacket(packet);
            }
        }
    }

    private static BufferedImage normalizeImageToMapSize(BufferedImage input) {
        return normalizeImageToSize(input, MAP_SIZE, MAP_SIZE);
    }

    private static BufferedImage normalizeImageToSize(BufferedImage input, int targetWidth, int targetHeight) {
        if (
                input.getWidth() == targetWidth
                        && input.getHeight() == targetHeight
                        && input.getType() == BufferedImage.TYPE_INT_ARGB
        ) {
            return input;
        }

        BufferedImage output = new BufferedImage(targetWidth, targetHeight, BufferedImage.TYPE_INT_ARGB);
        Graphics2D g = output.createGraphics();

        g.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BILINEAR);
        g.setRenderingHint(RenderingHints.KEY_RENDERING, RenderingHints.VALUE_RENDER_QUALITY);
        g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);

        g.drawImage(input, 0, 0, targetWidth, targetHeight, null);
        g.dispose();

        return output;
    }

    private static List<PaletteEntry> buildMapPalette() {
        List<PaletteEntry> result = new ArrayList<>();

        for (int colorId = 1; colorId < 64; colorId++) {
            MapColor baseColor = MapColor.get(colorId);

            if (baseColor == null || baseColor == MapColor.CLEAR) {
                continue;
            }

            for (MapColor.Brightness brightness : MapColor.Brightness.values()) {
                byte mapByte = baseColor.getRenderColorByte(brightness);
                int unsignedMapByte = Byte.toUnsignedInt(mapByte);

                if (unsignedMapByte == 0) {
                    continue;
                }

                int rgb = MapColor.getRenderColor(unsignedMapByte);
                int r = (rgb >> 16) & 255;
                int g = (rgb >> 8) & 255;
                int b = rgb & 255;

                result.add(new PaletteEntry(mapByte, r, g, b));
            }
        }

        return List.copyOf(result);
    }

    private static byte[] buildRgb15BitLookup() {
        byte[] lookup = new byte[32 * 32 * 32];

        for (int r5 = 0; r5 < 32; r5++) {
            for (int g5 = 0; g5 < 32; g5++) {
                for (int b5 = 0; b5 < 32; b5++) {
                    int r = (r5 << 3) + 4;
                    int g = (g5 << 3) + 4;
                    int b = (b5 << 3) + 4;

                    int index = (r5 << 10) | (g5 << 5) | b5;
                    lookup[index] = closestMapColorOpaque(r, g, b);
                }
            }
        }

        return lookup;
    }

    private static byte closestMapColorOpaque(int r, int g, int b) {
        byte bestColor = 0;
        long bestDistance = Long.MAX_VALUE;

        for (PaletteEntry entry : MAP_PALETTE) {
            int dr = r - entry.r();
            int dg = g - entry.g();
            int db = b - entry.b();

            long distance = (long) dr * dr + (long) dg * dg + (long) db * db;

            if (distance < bestDistance) {
                bestDistance = distance;
                bestColor = entry.mapByte();
            }
        }

        return bestColor;
    }

    private static byte closestMapColor(int argb) {
        int a = (argb >>> 24) & 255;

        if (a < 16) {
            return 0;
        }

        int r = (argb >> 16) & 255;
        int g = (argb >> 8) & 255;
        int b = argb & 255;

        if (a < 255) {
            r = (r * a + 255 * (255 - a)) / 255;
            g = (g * a + 255 * (255 - a)) / 255;
            b = (b * a + 255 * (255 - a)) / 255;
        }

        int index = ((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3);
        return RGB_15BIT_LOOKUP[index];
    }

    private static BlockPos getTileFrameBlockPos(BlockPos origin, int col, int row, Direction facing) {
        BlockPos base = origin.add(0, -row, 0);
        Direction horizontalStep = getScreenRightDirection(facing);

        return switch (horizontalStep) {
            case EAST -> base.add(col, 0, 0);
            case WEST -> base.add(-col, 0, 0);
            case SOUTH -> base.add(0, 0, col);
            case NORTH -> base.add(0, 0, -col);
            default -> base;
        };
    }

    private static BlockPos getBackingBlockPos(BlockPos framePos, Direction facing) {
        return framePos.offset(facing.getOpposite());
    }

    private static Direction getScreenRightDirection(Direction facing) {
        return switch (facing) {
            case SOUTH -> Direction.EAST;
            case NORTH -> Direction.WEST;
            case WEST -> Direction.SOUTH;
            case EAST -> Direction.NORTH;
            default -> Direction.EAST;
        };
    }

    private static Box makeScreenBox(BlockPos origin, int width, int height, Direction facing) {
        BlockPos a = getTileFrameBlockPos(origin, 0, 0, facing);
        BlockPos b = getTileFrameBlockPos(origin, width - 1, height - 1, facing);

        int minX = Math.min(a.getX(), b.getX());
        int minY = Math.min(a.getY(), b.getY());
        int minZ = Math.min(a.getZ(), b.getZ());

        int maxX = Math.max(a.getX(), b.getX());
        int maxY = Math.max(a.getY(), b.getY());
        int maxZ = Math.max(a.getZ(), b.getZ());

        return new Box(
                minX,
                minY,
                minZ,
                maxX + 1,
                maxY + 1,
                maxZ + 1
        );
    }

    private static Direction parseFacing(String raw) {
        String value = raw.toLowerCase(Locale.ROOT);

        return switch (value) {
            case "north" -> Direction.NORTH;
            case "south" -> Direction.SOUTH;
            case "east" -> Direction.EAST;
            case "west" -> Direction.WEST;
            default -> null;
        };
    }

    private static String formatPos(Vec3d pos) {
        return String.format(Locale.ROOT, "%.2f %.2f %.2f", pos.x, pos.y, pos.z);
    }

    private static void send(CommandContext<ServerCommandSource> context, String message) {
        context.getSource().sendFeedback(
                () -> Text.literal(message),
                false
        );
    }

    private record ClearResult(int frames, int barriers) {
    }

    private record GridWriteResult(
            int changedPixels,
            boolean resized,
            int originalWidth,
            int originalHeight,
            int targetWidth,
            int targetHeight
    ) {
    }

    private record CachedFrame(
            String name,
            byte[][] tiles,
            boolean resized,
            int originalWidth,
            int originalHeight,
            int targetWidth,
            int targetHeight
    ) {
    }

    private static final class PlaybackState {
        final RegistryKey<World> worldKey;
        final int startMapId;
        final int width;
        final int height;
        final Path frameDir;
        final List<Path> frameFiles;
        final BlockingQueue<CachedFrame> frameQueue;
        final int fps;
        final boolean loop;

        volatile boolean stopRequested = false;
        volatile boolean loaderDone = false;
        volatile String loaderError = null;

        volatile int decodedFrames = 0;
        volatile int playedFrames = 0;

        int tickAccumulator = 0;
        int lastChangedPixels = 0;
        String lastFrameName = null;
        String lastError = null;

        Thread loaderThread = null;

        PlaybackState(
                RegistryKey<World> worldKey,
                int startMapId,
                int width,
                int height,
                Path frameDir,
                List<Path> frameFiles,
                int fps,
                boolean loop
        ) {
            this.worldKey = worldKey;
            this.startMapId = startMapId;
            this.width = width;
            this.height = height;
            this.frameDir = frameDir;
            this.frameFiles = frameFiles;
            this.frameQueue = new ArrayBlockingQueue<>(STREAM_CACHE_FRAMES);
            this.fps = fps;
            this.loop = loop;
        }
    }

    private record PaletteEntry(byte mapByte, int r, int g, int b) {
    }
}