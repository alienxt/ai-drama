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

import java.time.LocalDate;
import java.util.List;

@RestController
@RequestMapping("/api/admin/hongguo")
public class HongguoDramaController {
    private final HongguoDramaService service;

    public HongguoDramaController(HongguoDramaService service) {
        this.service = service;
    }

    @GetMapping("/calendar-candidates")
    ApiResponse<List<HongguoDramaCandidate>> calendarCandidates(@RequestParam(required = false) LocalDate date) {
        return ApiResponse.ok(service.listCandidates(date), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PostMapping("/calendar-sync")
    ApiResponse<HongguoDtos.CalendarSyncResponse> syncCalendar(@RequestBody(required = false) HongguoDtos.CalendarSyncRequest request) {
        LocalDate date = request == null ? null : request.date();
        int page = request == null || request.page() == null ? 1 : request.page();
        return ApiResponse.ok(
                HongguoDtos.CalendarSyncResponse.from(service.syncCalendar(date, page)),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    @PostMapping("/candidates/{id}/import")
    ApiResponse<HongguoDtos.ImportCandidateResponse> importCandidate(@PathVariable String id) {
        Drama drama = service.importCandidate(id);
        return ApiResponse.ok(new HongguoDtos.ImportCandidateResponse(drama), MDC.get(TraceIdFilter.TRACE_ID));
    }
}
