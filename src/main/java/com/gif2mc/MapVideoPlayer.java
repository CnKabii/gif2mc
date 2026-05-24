package com.gif2mc;

import net.minecraft.component.type.MapIdComponent;
import net.minecraft.item.FilledMapItem;
import net.minecraft.item.map.MapState;
import net.minecraft.network.packet.s2c.play.MapUpdateS2CPacket;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.network.ServerPlayerEntity;
import net.minecraft.server.world.ServerWorld;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public class MapVideoPlayer {
    private static final int MAP_SIZE = 128;
    private static final int PIXELS = MAP_SIZE * MAP_SIZE;

    private MapIdComponent boundMapId;
    private ServerWorld boundWorld;
    private String loadedName = "<none>";
    private final List<byte[]> frames = new ArrayList<>();

    private boolean playing = false;
    private int frameIndex = 0;
    private int ticksPerFrame = 2; // 10 FPS by default.
    private int tickCounter = 0;

    public void bind(MapIdComponent mapId, ServerWorld world) {
        this.boundMapId = mapId;
        this.boundWorld = world;
    }

    public int load(String name, Path videoDir) throws Exception {
        List<byte[]> loaded = FrameLoader.loadPngFrames(videoDir, MAP_SIZE, MAP_SIZE);
        frames.clear();
        frames.addAll(loaded);
        loadedName = name;
        frameIndex = 0;
        tickCounter = 0;
        return frames.size();
    }

    public void play(int fps) {
        if (boundMapId == null || boundWorld == null) {
            throw new IllegalStateException("还没有绑定地图。先执行 /gif2mc newmap，或手持 filled_map 执行 /gif2mc bind。 ");
        }
        if (frames.isEmpty()) {
            throw new IllegalStateException("还没有加载帧。把 PNG 帧放进 world/gif2mc/videos/<name>/ 后执行 /gif2mc load <name>。 ");
        }
        ticksPerFrame = Math.max(1, Math.round(20.0f / Math.max(1, fps)));
        playing = true;
    }

    public void pause() {
        playing = false;
    }

    public void stop() {
        playing = false;
        frameIndex = 0;
        tickCounter = 0;
    }

    public void tick(MinecraftServer server) {
        if (!playing || frames.isEmpty() || boundMapId == null || boundWorld == null) {
            return;
        }

        tickCounter++;
        if (tickCounter < ticksPerFrame) {
            return;
        }
        tickCounter = 0;

        byte[] frame = frames.get(frameIndex);
        writeFrame(boundWorld, boundMapId, frame, server);
        frameIndex = (frameIndex + 1) % frames.size();
    }

    private void writeFrame(ServerWorld world, MapIdComponent mapId, byte[] frame, MinecraftServer server) {
        MapState state = FilledMapItem.getMapState(mapId, world);
        if (state == null) {
            playing = false;
            return;
        }

        for (int z = 0; z < MAP_SIZE; z++) {
            int rowOffset = z * MAP_SIZE;
            for (int x = 0; x < MAP_SIZE; x++) {
                state.putColor(x, z, frame[rowOffset + x]);
            }
        }

        // Force a full vanilla map update packet. This keeps item-frame playback responsive too,
        // instead of relying only on inventory-held map tracking.
        MapState.UpdateData update = new MapState.UpdateData(0, 0, MAP_SIZE, MAP_SIZE, frame.clone());
        MapUpdateS2CPacket packet = new MapUpdateS2CPacket(mapId, (byte) 0, false, null, update);
        for (ServerPlayerEntity player : server.getPlayerManager().getPlayerList()) {
            player.networkHandler.sendPacket(packet);
        }
    }

    public String status() {
        String map = boundMapId == null ? "<none>" : "map_" + boundMapId.id();
        return "GIF2MC MVP status: map=" + map +
            ", video=" + loadedName +
            ", frames=" + frames.size() +
            ", frameIndex=" + frameIndex +
            ", playing=" + playing +
            ", ticksPerFrame=" + ticksPerFrame;
    }
}
