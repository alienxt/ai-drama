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
        double minutesPerEpisode = 1 + random.nextDouble();
        int rounded = (int) Math.round((episodeCount * minutesPerEpisode) / 10.0) * 10;
        return Math.max(10, rounded);
    }

    public static int estimateTotalMinutes(Drama drama) {
        int episodeCount = drama.getEpisodes() == null ? 0 : drama.getEpisodes().size();
        return estimateTotalMinutes(episodeCount, seedText(drama));
    }

    public static boolean needsTotalMinutes(Drama drama) {
        Integer totalMinutes = drama.getTotalMinutes();
        return totalMinutes == null || totalMinutes <= 0 || totalMinutes % 10 != 0;
    }

    public static int estimateCostAmountWan(String seedText) {
        Random random = new Random(seed("cost:" + (seedText == null ? "" : seedText)));
        return 1 + random.nextInt(5);
    }

    public static int estimateCostAmountWan(Drama drama) {
        return estimateCostAmountWan(seedText(drama));
    }

    public static boolean needsCostAmountWan(Drama drama) {
        Integer costAmountWan = drama.getCostAmountWan();
        return costAmountWan == null || costAmountWan <= 0;
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
