package com.onehot.aidrama.logs;

import com.onehot.aidrama.common.ApiResponse;
import com.onehot.aidrama.common.PageResult;
import com.onehot.aidrama.common.TraceIdFilter;
import org.slf4j.MDC;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;

@RestController
@RequestMapping("/api/admin")
@PreAuthorize("hasRole('ADMIN')")
public class LogController {
    private final MongoTemplate mongoTemplate;

    public LogController(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    @GetMapping("/request-logs")
    ApiResponse<PageResult<LogDtos.RequestLogResponse>> requestLogs(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) String method,
            @RequestParam(required = false) Integer status,
            @RequestParam(required = false) String traceId,
            @RequestParam(required = false) String username,
            @RequestParam(required = false) Instant from,
            @RequestParam(required = false) Instant to,
            Pageable pageable
    ) {
        return ApiResponse.ok(PageResult.from(new LogQuery()
                .keyword(keyword)
                .method(method)
                .status(status)
                .traceId(traceId)
                .username(username)
                .createdBetween(from, to)
                .page(mongoTemplate, RequestLog.class, pageable)
                .map(LogDtos.RequestLogResponse::from)), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @GetMapping("/exception-logs")
    ApiResponse<PageResult<LogDtos.ExceptionLogResponse>> exceptionLogs(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) String method,
            @RequestParam(required = false) Integer status,
            @RequestParam(required = false) String traceId,
            @RequestParam(required = false) String username,
            @RequestParam(required = false) Instant from,
            @RequestParam(required = false) Instant to,
            Pageable pageable
    ) {
        return ApiResponse.ok(PageResult.from(new LogQuery()
                .keyword(keyword)
                .method(method)
                .status(status)
                .traceId(traceId)
                .username(username)
                .createdBetween(from, to)
                .page(mongoTemplate, ExceptionLog.class, pageable)
                .map(LogDtos.ExceptionLogResponse::from)), MDC.get(TraceIdFilter.TRACE_ID));
    }
}
