package com.onehot.aidrama.system;

import com.onehot.aidrama.common.ApiResponse;
import com.onehot.aidrama.common.MongoPageQuery;
import com.onehot.aidrama.common.PageResult;
import com.onehot.aidrama.common.TraceIdFilter;
import org.slf4j.MDC;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SystemTaskController {
    private final MongoTemplate mongoTemplate;

    public SystemTaskController(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    @GetMapping("/api/admin/system-tasks")
    ApiResponse<PageResult<SystemTask>> list(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) SystemTaskType type,
            @RequestParam(required = false) SystemTaskStatus status,
            Pageable pageable
    ) {
        MongoPageQuery query = new MongoPageQuery()
                .containsAny(keyword, "id", "title", "summary", "errorMessage")
                .eq("type", type)
                .eq("status", status);
        return ApiResponse.ok(
                PageResult.from(query.page(mongoTemplate, SystemTask.class, pageable)),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }
}
