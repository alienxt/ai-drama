package com.onehot.aidrama.hongguo;

import com.onehot.aidrama.dramas.Drama;

public class HongguoDtos {
    private HongguoDtos() {
    }

    public record MangaSearchRequest(String keyword, Integer page) {
    }

    public record NewDramaRequest(Integer page) {
    }

    public record MangaSearchResponse(String keyword, int page, int fetched, int detailed, int skipped, int created, int updated) {
        static MangaSearchResponse from(HongguoDramaService.MangaSearchResult result) {
            return new MangaSearchResponse(
                    result.keyword(),
                    result.page(),
                    result.fetched(),
                    result.detailed(),
                    result.skipped(),
                    result.created(),
                    result.updated()
            );
        }
    }

    public record ImportCandidateResponse(Drama drama) {
    }
}
