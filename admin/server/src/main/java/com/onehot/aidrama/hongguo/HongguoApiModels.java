package com.onehot.aidrama.hongguo;

import java.time.Instant;
import java.util.List;

public class HongguoApiModels {
    private HongguoApiModels() {
    }

    public record MangaSearchPage(String keyword, int page, List<MangaSearchItem> items) {
    }

    public record MangaSearchItem(
            String providerDramaId,
            String title,
            String summary,
            String coverUrl,
            String duration,
            String score,
            String category,
            String copyright,
            Integer episodeCount,
            Long playCount,
            Instant publishedAt,
            List<String> categories,
            List<String> recTags
    ) {
    }

    public record DramaDetail(
            String providerDramaId,
            String title,
            String summary,
            String coverUrl,
            Integer episodeCount,
            Integer durationSeconds,
            Long playCount,
            Instant publishedAt,
            List<DetailEpisode> episodes
    ) {
    }

    public record DetailEpisode(
            int episodeNo,
            String title,
            String providerVideoId,
            Integer durationSeconds
    ) {
    }

    public record VideoVariant(
            String url,
            String decryptKey,
            String definition,
            String duration,
            String size,
            Integer width,
            Integer height
    ) {
    }

    public record DecryptedUrl(String url, Instant expiresAt) {
    }
}
