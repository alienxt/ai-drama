package com.onehot.aidrama.hongguo;

import com.onehot.aidrama.dramas.Drama;

import java.util.List;

public class HongguoDtos {
    private HongguoDtos() {
    }

    public record MangaSearchRequest(String keyword, Integer page) {
    }

    public record NewDramaRequest(Integer page, Integer maxPages) {
    }

    public record MangaSearchResponse(String keyword, int page, int fetched, int detailed, int skipped, int created, int updated, List<HongguoDramaCandidate> candidates) {
        static MangaSearchResponse from(HongguoDramaService.MangaSearchResult result) {
            return from(result, List.of());
        }

        static MangaSearchResponse from(HongguoDramaService.MangaSearchResult result, List<HongguoDramaCandidate> candidates) {
            return new MangaSearchResponse(
                    result.keyword(),
                    result.page(),
                    result.fetched(),
                    result.detailed(),
                    result.skipped(),
                    result.created(),
                    result.updated(),
                    candidates == null ? List.of() : candidates
            );
        }
    }

    public record ImportCandidateResponse(Drama drama) {
    }

    public record OtherChannelResponse(
            String code,
            String label,
            String mode,
            boolean keywordSupported,
            boolean optionRequired,
            String defaultKeyword
    ) {
        static OtherChannelResponse from(OtherShortDramaChannel channel) {
            return new OtherChannelResponse(
                    channel.code(),
                    channel.label(),
                    channel.mode().name(),
                    channel.supportsKeyword(),
                    channel.needsOption(),
                    channel.defaultKeyword()
            );
        }
    }

    public record OtherChannelOptionResponse(String id, String label) {
        static OtherChannelOptionResponse from(HongguoApiModels.ChannelOption option) {
            return new OtherChannelOptionResponse(option.id(), option.label());
        }
    }

    public record OtherChannelSyncRequest(String keyword, Integer page, String optionId) {
    }
}
