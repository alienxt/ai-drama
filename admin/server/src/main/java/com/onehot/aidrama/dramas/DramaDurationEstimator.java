package com.onehot.aidrama.dramas;

import java.nio.charset.StandardCharsets;
import java.util.Random;
import java.util.zip.CRC32;

public final class DramaDurationEstimator {
    private DramaDurationEstimator() {
    }

    public static int estimateTotalMinutes(int episodeCount, String seedText) {
        if (episodeCount <= 0) {
            return 0;
        }
        Random random = new Random(seed(seedText));
        int total = 0;
        for (int index = 0; index < episodeCount; index += 1) {
            total += 1 + random.nextInt(2);
        }
        return total;
    }

    public static int estimateTotalMinutes(Drama drama) {
        int episodeCount = drama.getEpisodes() == null ? 0 : drama.getEpisodes().size();
        return estimateTotalMinutes(episodeCount, seedText(drama));
    }

    public static boolean needsTotalMinutes(Drama drama) {
        return drama.getTotalMinutes() == null || drama.getTotalMinutes() <= 0;
    }

    private static String seedText(Drama drama) {
        if (drama.getSourcePath() != null && !drama.getSourcePath().isBlank()) {
            return drama.getSourcePath();
        }
        if (drama.getTitle() != null && !drama.getTitle().isBlank()) {
            return drama.getTitle();
        }
        return drama.getId() == null ? "" : drama.getId();
    }

    private static long seed(String seedText) {
        CRC32 crc32 = new CRC32();
        crc32.update((seedText == null ? "" : seedText).getBytes(StandardCharsets.UTF_8));
        return crc32.getValue();
    }
}
