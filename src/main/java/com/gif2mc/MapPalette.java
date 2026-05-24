package com.gif2mc;

import net.minecraft.block.MapColor;

import java.awt.image.BufferedImage;

public final class MapPalette {
    private static final int MAP_SIZE = 128;
    private static final PaletteEntry[] PALETTE = buildPalette();

    private MapPalette() {
    }

    public static byte[] convertImage(BufferedImage image) {
        byte[] out = new byte[MAP_SIZE * MAP_SIZE];
        for (int y = 0; y < MAP_SIZE; y++) {
            for (int x = 0; x < MAP_SIZE; x++) {
                int argb = image.getRGB(x, y);
                int alpha = (argb >>> 24) & 0xFF;
                if (alpha < 16) {
                    out[y * MAP_SIZE + x] = 0;
                    continue;
                }
                int r = (argb >>> 16) & 0xFF;
                int g = (argb >>> 8) & 0xFF;
                int b = argb & 0xFF;
                out[y * MAP_SIZE + x] = nearest(r, g, b);
            }
        }
        return out;
    }

    private static byte nearest(int r, int g, int b) {
        int bestDistance = Integer.MAX_VALUE;
        byte best = 0;
        for (PaletteEntry entry : PALETTE) {
            int dr = r - entry.r;
            int dg = g - entry.g;
            int db = b - entry.b;
            int distance = dr * dr + dg * dg + db * db;
            if (distance < bestDistance) {
                bestDistance = distance;
                best = entry.colorByte;
            }
        }
        return best;
    }

    private static PaletteEntry[] buildPalette() {
        // 0 is transparent/clear. Normal visible map colors are encoded as baseColor * 4 + brightness.
        PaletteEntry[] entries = new PaletteEntry[255];
        int count = 0;
        for (int colorByte = 1; colorByte <= 255; colorByte++) {
            int rgb = MapColor.getRenderColor(colorByte);
            int r = (rgb >>> 16) & 0xFF;
            int g = (rgb >>> 8) & 0xFF;
            int b = rgb & 0xFF;
            // Some unused ids render as black-ish entries; keeping them is harmless for MVP.
            entries[count++] = new PaletteEntry((byte) colorByte, r, g, b);
        }
        return entries;
    }

    private record PaletteEntry(byte colorByte, int r, int g, int b) {
    }
}
