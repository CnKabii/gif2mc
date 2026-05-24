package com.gif2mc;

import javax.imageio.ImageIO;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;

public final class FrameLoader {
    private FrameLoader() {
    }

    public static List<byte[]> loadPngFrames(Path dir, int width, int height) throws IOException {
        if (!Files.isDirectory(dir)) {
            throw new IOException("目录不存在：" + dir);
        }

        List<Path> files;
        try (Stream<Path> stream = Files.list(dir)) {
            files = stream
                .filter(Files::isRegularFile)
                .filter(path -> path.getFileName().toString().toLowerCase(Locale.ROOT).endsWith(".png"))
                .sorted(Comparator.comparing(path -> path.getFileName().toString()))
                .toList();
        }

        if (files.isEmpty()) {
            throw new IOException("目录里没有 PNG 帧：" + dir);
        }

        return files.stream().map(path -> {
            try {
                BufferedImage image = ImageIO.read(path.toFile());
                if (image == null) {
                    throw new IOException("不是有效 PNG：" + path);
                }
                BufferedImage scaled = scaleToMap(image, width, height);
                return MapPalette.convertImage(scaled);
            } catch (IOException e) {
                throw new RuntimeException(e);
            }
        }).toList();
    }

    private static BufferedImage scaleToMap(BufferedImage image, int width, int height) {
        if (image.getWidth() == width && image.getHeight() == height && image.getType() == BufferedImage.TYPE_INT_ARGB) {
            return image;
        }
        BufferedImage out = new BufferedImage(width, height, BufferedImage.TYPE_INT_ARGB);
        Graphics2D g = out.createGraphics();
        try {
            g.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BILINEAR);
            g.drawImage(image, 0, 0, width, height, null);
        } finally {
            g.dispose();
        }
        return out;
    }
}
