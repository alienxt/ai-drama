package com.onehot.aidrama.dramas;

import java.time.Instant;
import java.util.List;

public class DramaDtos {
    public record DramaRequest(
            String title,
            String aiTitle,
            String aiTitleEn,
            String summary,
            String aiSummary,
            String aiSummaryEn,
            String coverUrl,
            String aiCoverUrl,
            String aiVideoCoverUrl,
            String aiCoverEnUrl,
            String aiVideoCoverEnUrl,
            Integer rating,
            Integer costAmountWan,
            List<String> categoryIds,
            DramaStatus status
    ) {
    }

    public record BatchIdsRequest(List<String> ids) {
    }

    public record BatchFreshResponse(int requested, long updated, Instant updatedAt) {
    }

    public record BackfillTotalMinutesResponse(int requested, long updated, Instant updatedAt) {
    }

    public record BackfillAiSummariesAccepted(int requested, Instant acceptedAt) {
    }

    public record DownloadPlan(
            String dramaId,
            String title,
            String aiTitle,
            String aiTitleEn,
            String summary,
            String aiSummary,
            String aiSummaryEn,
            String coverUrl,
            String aiCoverUrl,
            String aiVideoCoverUrl,
            String aiCoverEnUrl,
            String aiVideoCoverEnUrl,
            String effectiveCoverUrl,
            Integer rating,
            Integer totalMinutes,
            Integer costAmountWan,
            List<String> categoryIds,
            List<EpisodeDownload> episodes
    ) {
    }

    public record EpisodeDownload(int episodeNo, String sourcePath, long size, String downloadUrl) {
    }

    public record AdminEpisodeResponse(
            int episodeNo,
            String title,
            String sourcePath,
            long size,
            boolean downloaded,
            String playSource,
            String localUrl
    ) {
    }

    public record EpisodePlaySource(int episodeNo, String source, boolean downloaded, String playUrl) {
    }

    public record DesktopDramaResponse(
            String id,
            String title,
            String aiTitle,
            String aiTitleEn,
            String summary,
            String aiSummary,
            String aiSummaryEn,
            String coverUrl,
            String aiCoverUrl,
            String aiVideoCoverUrl,
            String aiCoverEnUrl,
            String aiVideoCoverEnUrl,
            Integer rating,
            List<String> categoryIds,
            List<String> categoryNames,
            int episodeCount,
            int totalMinutes,
            int costAmountWan,
            Instant createdAt,
            Instant updatedAt,
            DramaStatus status,
            String preparationStatus,
            boolean prioritized
    ) {
        public static DesktopDramaResponse from(
                String id,
                String title,
                String aiTitle,
                String aiTitleEn,
                String summary,
                String aiSummary,
                String aiSummaryEn,
                String coverUrl,
                String aiCoverUrl,
                String aiVideoCoverUrl,
                String aiCoverEnUrl,
                String aiVideoCoverEnUrl,
                Integer rating,
                List<String> categoryIds,
                List<String> categoryNames,
                int episodeCount,
                int totalMinutes,
                int costAmountWan,
                Instant createdAt,
                Instant updatedAt,
                DramaStatus status,
                boolean prioritized
        ) {
            DramaStatus effectiveStatus = status == null ? DramaStatus.DRAFT : status;
            return new DesktopDramaResponse(
                    id,
                    effectiveTitle(title, aiTitle),
                    null,
                    aiTitleEn,
                    summary,
                    aiSummary,
                    aiSummaryEn,
                    effectiveCoverUrl(coverUrl, aiCoverUrl),
                    null,
                    aiVideoCoverUrl,
                    aiCoverEnUrl,
                    aiVideoCoverEnUrl,
                    rating == null ? 5 : rating,
                    categoryIds == null ? List.of() : categoryIds,
                    categoryNames,
                    episodeCount,
                    totalMinutes,
                    costAmountWan,
                    createdAt,
                    updatedAt,
                    effectiveStatus,
                    preparationStatus(effectiveStatus),
                    prioritized
            );
        }

        private static String effectiveTitle(String title, String aiTitle) {
            if (aiTitle != null && !aiTitle.isBlank()) {
                return aiTitle;
            }
            return title;
        }

        private static String effectiveCoverUrl(String coverUrl, String aiCoverUrl) {
            if (aiCoverUrl != null && !aiCoverUrl.isBlank()) {
                return aiCoverUrl;
            }
            return coverUrl;
        }

        private static String preparationStatus(DramaStatus status) {
            return status == DramaStatus.READY ? "READY" : "PENDING_AI_ASSETS";
        }
    }
}
