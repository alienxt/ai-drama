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

    @GetMapping("/ai-playlet-new-top-candidates")
    ApiResponse<List<HongguoDramaCandidate>> aiPlayletNewTopCandidates(@RequestParam(required = false) Integer page) {
        return ApiResponse.ok(service.listAiPlayletNewTopDramas(page), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PostMapping("/ai-playlet-new-top-sync")
    ApiResponse<HongguoDtos.MangaSearchResponse> syncAiPlayletNewTop(@RequestBody(required = false) HongguoDtos.NewDramaRequest request) {
        int page = request == null || request.page() == null ? 1 : request.page();
        return ApiResponse.ok(
                HongguoDtos.MangaSearchResponse.from(service.syncAiPlayletNewTopDramas(page)),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    @GetMapping("/ai-manga-new-candidates")
    ApiResponse<List<HongguoDramaCandidate>> aiMangaNewCandidates(@RequestParam(required = false) Integer page) {
        return ApiResponse.ok(service.listAiMangaNewDramas(page), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PostMapping("/ai-manga-new-sync")
    ApiResponse<HongguoDtos.MangaSearchResponse> syncAiMangaNew(@RequestBody(required = false) HongguoDtos.NewDramaRequest request) {
        int maxPages = request == null || request.maxPages() == null
                ? HongguoDramaService.DEFAULT_AI_MANGA_SYNC_MAX_PAGES
                : request.maxPages();
        return ApiResponse.ok(
                HongguoDtos.MangaSearchResponse.from(service.syncAiMangaNewDramas(maxPages)),
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

    @GetMapping("/other-channels")
    ApiResponse<List<HongguoDtos.OtherChannelResponse>> otherChannels() {
        return ApiResponse.ok(
                OtherShortDramaChannel.visibleChannels().stream()
                        .map(HongguoDtos.OtherChannelResponse::from)
                        .toList(),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    @GetMapping("/other-channels/{channel}/options")
    ApiResponse<List<HongguoDtos.OtherChannelOptionResponse>> otherChannelOptions(@PathVariable String channel) {
        return ApiResponse.ok(
                service.listOtherChannelOptions(channel).stream()
                        .map(HongguoDtos.OtherChannelOptionResponse::from)
                        .toList(),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    @GetMapping("/other-channels/{channel}/candidates")
    ApiResponse<List<HongguoDramaCandidate>> otherChannelCandidates(
            @PathVariable String channel,
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) String optionId,
            @RequestParam(required = false) Integer page
    ) {
        return ApiResponse.ok(
                service.listOtherChannelCandidates(channel, keyword, optionId, page),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    @PostMapping("/other-channels/{channel}/sync")
    ApiResponse<HongguoDtos.MangaSearchResponse> syncOtherChannel(
            @PathVariable String channel,
            @RequestBody(required = false) HongguoDtos.OtherChannelSyncRequest request
    ) {
        String keyword = request == null ? null : request.keyword();
        String optionId = request == null ? null : request.optionId();
        int page = request == null || request.page() == null ? 1 : request.page();
        return ApiResponse.ok(
                HongguoDtos.MangaSearchResponse.from(service.syncOtherChannel(channel, keyword, optionId, page)),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    @PostMapping("/backfill-covers")
    ApiResponse<HongguoDramaService.CoverBackfillResult> backfillCovers() {
        return ApiResponse.ok(service.backfillCovers(), MDC.get(TraceIdFilter.TRACE_ID));
    }
}
