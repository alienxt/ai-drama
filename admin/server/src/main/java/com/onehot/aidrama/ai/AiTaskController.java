package com.onehot.aidrama.ai;

import com.onehot.aidrama.common.ApiResponse;
import com.onehot.aidrama.common.MongoPageQuery;
import com.onehot.aidrama.common.PageResult;
import com.onehot.aidrama.common.TraceIdFilter;
import com.onehot.aidrama.dramas.Drama;
import com.onehot.aidrama.dramas.DramaRepository;
import org.slf4j.MDC;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Optional;

@RestController
public class AiTaskController {
    private final MongoTemplate mongoTemplate;
    private final DramaRepository dramaRepository;

    public AiTaskController(MongoTemplate mongoTemplate, DramaRepository dramaRepository) {
        this.mongoTemplate = mongoTemplate;
        this.dramaRepository = dramaRepository;
    }

    @GetMapping("/api/admin/ai-tasks")
    ApiResponse<PageResult<AiTaskDtos.AdminAiTaskResponse>> list(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) AiTaskType type,
            @RequestParam(required = false) AiTaskStatus status,
            Pageable pageable
    ) {
        MongoPageQuery query = new MongoPageQuery()
                .containsAny(keyword, "id", "subjectId", "prompt", "errorMessage")
                .eq("type", type)
                .eq("status", status);
        PageResult<AiTask> page = PageResult.from(query.page(mongoTemplate, AiTask.class, pageable));
        var rows = page.content().stream()
                .map(task -> AiTaskDtos.AdminAiTaskResponse.from(task, subjectTitle(task)))
                .toList();
        return ApiResponse.ok(
                new PageResult<>(rows, page.totalElements(), page.totalPages(), page.page(), page.size()),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    private String subjectTitle(AiTask task) {
        if (!"DRAMA".equals(task.getSubjectType()) || task.getSubjectId() == null) {
            return null;
        }
        return dramaRepository.findById(task.getSubjectId())
                .map(this::dramaTitle)
                .orElse(task.getSubjectId());
    }

    private String dramaTitle(Drama drama) {
        return Optional.ofNullable(drama.getAiTitle())
                .filter(value -> !value.isBlank())
                .orElse(drama.getTitle());
    }
}
