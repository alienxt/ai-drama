package com.onehot.aidrama.dramas;

import java.time.Instant;
import java.util.List;

public class DramaDtos {
    public record DramaRequest(
            String title,
            String aiTitle,
            String summary,
            String coverUrl,
            String aiCoverUrl,
            Integer rating,
            List<String> categoryIds,
            DramaStatus status
    ) {
    }

    public record DownloadPlan(
            String dramaId,
            String title,
            String aiTitle,
            String summary,
            String coverUrl,
            String aiCoverUrl,
            String effectiveCoverUrl,
            Integer rating,
            List<String> categoryIds,
            List<EpisodeDownload> episodes
    ) {
    }

    public record EpisodeDownload(int episodeNo, String sourcePath, String downloadUrl) {
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
            String summary,
            String coverUrl,
            String aiCoverUrl,
            Integer rating,
            List<String> categoryIds,
            List<String> categoryNames,
            int episodeCount,
            Instant createdAt,
            boolean prioritized
    ) {
        public static DesktopDramaResponse from(
                String id,
                String title,
                String aiTitle,
                String summary,
                String coverUrl,
                String aiCoverUrl,
                Integer rating,
                List<String> categoryIds,
                List<String> categoryNames,
                int episodeCount,
                Instant createdAt,
                boolean prioritized
        ) {
            return new DesktopDramaResponse(
                    id,
                    effectiveTitle(title, aiTitle),
                    null,
                    summary,
                    effectiveCoverUrl(coverUrl, aiCoverUrl),
                    null,
                    rating == null ? 5 : rating,
                    categoryIds == null ? List.of() : categoryIds,
                    categoryNames,
                    episodeCount,
                    createdAt,
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
    }
}
