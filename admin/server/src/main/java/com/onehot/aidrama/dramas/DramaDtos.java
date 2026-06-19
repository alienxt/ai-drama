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
            List<DramaEpisode> episodes,
            Instant createdAt,
            boolean prioritized
    ) {
        public static DesktopDramaResponse from(Drama drama, List<String> categoryNames, boolean prioritized) {
            return new DesktopDramaResponse(
                    drama.getId(),
                    effectiveTitle(drama),
                    null,
                    drama.getSummary(),
                    effectiveCoverUrl(drama),
                    null,
                    drama.getRating(),
                    drama.getCategoryIds(),
                    categoryNames,
                    drama.getEpisodes(),
                    drama.getCreatedAt(),
                    prioritized
            );
        }

        private static String effectiveTitle(Drama drama) {
            if (drama.getAiTitle() != null && !drama.getAiTitle().isBlank()) {
                return drama.getAiTitle();
            }
            return drama.getTitle();
        }

        private static String effectiveCoverUrl(Drama drama) {
            if (drama.getAiCoverUrl() != null && !drama.getAiCoverUrl().isBlank()) {
                return drama.getAiCoverUrl();
            }
            return drama.getCoverUrl();
        }
    }
}
