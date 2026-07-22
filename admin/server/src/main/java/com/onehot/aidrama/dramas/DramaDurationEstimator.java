package com.onehot.aidrama.dramas;

import java.nio.charset.StandardCharsets;
import java.util.Random;
import java.util.zip.CRC32;

public final class DramaDurationEstimator {
    private static final int MIN_COST_AMOUNT_WAN = 2;
    private static final int MAX_COST_AMOUNT_WAN = 20;
    private static final int COST_STEP_MINUTES = 10;

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

    public static int estimateCostAmountWan(int totalMinutes) {
        int cost = (int) Math.ceil(Math.max(totalMinutes, 1) / (double) COST_STEP_MINUTES);
        return Math.max(MIN_COST_AMOUNT_WAN, Math.min(MAX_COST_AMOUNT_WAN, cost));
    }

    public static int estimateCostAmountWan(Drama drama) {
        int totalMinutes = drama.getTotalMinutes();
        if (totalMinutes <= 0) {
            totalMinutes = estimateTotalMinutes(drama);
        }
        return estimateCostAmountWan(totalMinutes);
    }

    public static boolean needsCostAmountWan(Drama drama) {
        Integer costAmountWan = drama.getCostAmountWan();
        return costAmountWan == null || costAmountWan <= 0 || costAmountWan != estimateCostAmountWan(drama);
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
