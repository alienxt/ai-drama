package com.onehot.aidrama.configs;

import com.onehot.aidrama.common.ApiResponse;
import com.onehot.aidrama.common.MongoPageQuery;
import com.onehot.aidrama.common.PageResult;
import com.onehot.aidrama.common.TraceIdFilter;
import org.slf4j.MDC;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/admin/configs")
public class SystemConfigController {
    private final SystemConfigRepository repository;
    private final SystemConfigService service;
    private final MongoTemplate mongoTemplate;

    public SystemConfigController(SystemConfigRepository repository, SystemConfigService service, MongoTemplate mongoTemplate) {
        this.repository = repository;
        this.service = service;
        this.mongoTemplate = mongoTemplate;
    }

    @GetMapping
    ApiResponse<PageResult<ConfigDtos.ConfigResponse>> list(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Boolean secret,
            Pageable pageable
    ) {
        return ApiResponse.ok(PageResult.from(new MongoPageQuery()
                .containsAny(keyword, "key", "value")
                .eq("secret", secret)
                .page(mongoTemplate, SystemConfig.class, pageable)
                .map(ConfigDtos.ConfigResponse::from)), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PutMapping("/{key}")
    ApiResponse<ConfigDtos.ConfigResponse> put(@PathVariable String key, @RequestBody ConfigDtos.ConfigRequest request) {
        SystemConfig config = repository.findByKey(key).orElseGet(SystemConfig::new);
        config = service.put(key, request.value(), request.secret());
        return ApiResponse.ok(ConfigDtos.ConfigResponse.from(config), MDC.get(TraceIdFilter.TRACE_ID));
    }
}
