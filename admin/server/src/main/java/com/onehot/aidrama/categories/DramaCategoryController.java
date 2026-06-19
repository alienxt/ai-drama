package com.onehot.aidrama.categories;

import com.onehot.aidrama.common.ApiResponse;
import com.onehot.aidrama.common.MongoPageQuery;
import com.onehot.aidrama.common.PageResult;
import com.onehot.aidrama.common.TraceIdFilter;
import jakarta.validation.Valid;
import org.slf4j.MDC;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
public class DramaCategoryController {
    private final DramaCategoryRepository repository;
    private final MongoTemplate mongoTemplate;

    public DramaCategoryController(DramaCategoryRepository repository, MongoTemplate mongoTemplate) {
        this.repository = repository;
        this.mongoTemplate = mongoTemplate;
    }

    @GetMapping("/api/admin/categories")
    ApiResponse<PageResult<DramaCategory>> adminList(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Boolean enabled,
            Pageable pageable
    ) {
        return ApiResponse.ok(PageResult.from(new MongoPageQuery()
                .containsAny(keyword, "name", "code")
                .eq("enabled", enabled)
                .page(mongoTemplate, DramaCategory.class, pageable)), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @GetMapping("/api/desktop/categories")
    ApiResponse<List<DramaCategory>> desktopList() {
        return ApiResponse.ok(repository.findByEnabledTrueOrderBySortOrderAsc(), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PostMapping("/api/admin/categories")
    ApiResponse<DramaCategory> create(@Valid @RequestBody CategoryRequest request) {
        return ApiResponse.ok(repository.save(apply(new DramaCategory(), request)), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PutMapping("/api/admin/categories/{id}")
    ApiResponse<DramaCategory> update(@PathVariable String id, @Valid @RequestBody CategoryRequest request) {
        DramaCategory category = repository.findById(id).orElseThrow();
        return ApiResponse.ok(repository.save(apply(category, request)), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @DeleteMapping("/api/admin/categories/{id}")
    ApiResponse<Void> delete(@PathVariable String id) {
        repository.deleteById(id);
        return ApiResponse.ok(null, MDC.get(TraceIdFilter.TRACE_ID));
    }

    private DramaCategory apply(DramaCategory category, CategoryRequest request) {
        category.setName(request.name());
        category.setCode(request.code());
        category.setEnabled(request.enabled());
        category.setSortOrder(request.sortOrder());
        return category;
    }
}
