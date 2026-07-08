package com.onehot.aidrama.hongguo;

import com.onehot.aidrama.common.ApiResponse;
import com.onehot.aidrama.common.TraceIdFilter;
import com.onehot.aidrama.dramas.Drama;
import org.slf4j.MDC;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/admin/hongguo")
public class HongguoDramaController {
    private final HongguoDramaService service;

    public HongguoDramaController(HongguoDramaService service) {
        this.service = service;
    }

    @GetMapping("/manga-candidates")
    ApiResponse<List<HongguoDramaCandidate>> mangaCandidates(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Integer page
    ) {
        return ApiResponse.ok(service.listMangaCandidates(keyword, page), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PostMapping("/manga-sync")
    ApiResponse<HongguoDtos.MangaSearchResponse> syncManga(@RequestBody(required = false) HongguoDtos.MangaSearchRequest request) {
        String keyword = request == null ? null : request.keyword();
        int page = request == null || request.page() == null ? 1 : request.page();
        return ApiResponse.ok(
                HongguoDtos.MangaSearchResponse.from(service.syncMangaSearch(keyword, page)),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    @GetMapping("/new-candidates")
    ApiResponse<List<HongguoDramaCandidate>> newCandidates(@RequestParam(required = false) Integer page) {
        return ApiResponse.ok(service.listNewDramas(page), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PostMapping("/new-sync")
    ApiResponse<HongguoDtos.MangaSearchResponse> syncNew(@RequestBody(required = false) HongguoDtos.NewDramaRequest request) {
        int page = request == null || request.page() == null ? 1 : request.page();
        return ApiResponse.ok(
                HongguoDtos.MangaSearchResponse.from(service.syncNewDramas(page)),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    @GetMapping("/calendar-candidates")
    ApiResponse<List<HongguoDramaCandidate>> calendarCandidates(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Integer page
    ) {
        return mangaCandidates(keyword, page);
    }

    @PostMapping("/calendar-sync")
    ApiResponse<HongguoDtos.MangaSearchResponse> syncCalendar(@RequestBody(required = false) HongguoDtos.MangaSearchRequest request) {
        return syncManga(request);
    }

    @PostMapping("/candidates/{id}/import")
    ApiResponse<HongguoDtos.ImportCandidateResponse> importCandidate(@PathVariable String id) {
        Drama drama = service.importCandidate(id);
        return ApiResponse.ok(new HongguoDtos.ImportCandidateResponse(drama), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PostMapping("/backfill-covers")
    ApiResponse<HongguoDramaService.CoverBackfillResult> backfillCovers() {
        return ApiResponse.ok(service.backfillCovers(), MDC.get(TraceIdFilter.TRACE_ID));
    }
}
