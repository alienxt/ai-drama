package com.onehot.aidrama.versions;

import com.onehot.aidrama.common.ApiResponse;
import com.onehot.aidrama.common.PageResult;
import com.onehot.aidrama.common.TraceIdFilter;
import org.slf4j.MDC;
import org.springframework.data.domain.Pageable;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
public class DesktopVersionController {
    private final DesktopVersionRepository repository;
    private final DesktopVersionService service;
    private final DesktopVersionStorage storage;

    public DesktopVersionController(
            DesktopVersionRepository repository,
            DesktopVersionService service,
            DesktopVersionStorage storage
    ) {
        this.repository = repository;
        this.service = service;
        this.storage = storage;
    }

    @GetMapping("/api/admin/desktop-versions")
    ApiResponse<PageResult<VersionDtos.VersionResponse>> list(Pageable pageable) {
        return ApiResponse.ok(
                PageResult.from(repository.findAll(pageable).map(VersionDtos.VersionResponse::from)),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    @PostMapping("/api/admin/desktop-versions")
    ApiResponse<VersionDtos.VersionResponse> create(@RequestBody VersionDtos.VersionRequest request) {
        return ApiResponse.ok(VersionDtos.VersionResponse.from(service.create(request)), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PostMapping("/api/admin/desktop-versions/{id}/package")
    ApiResponse<VersionDtos.VersionResponse> upload(@PathVariable String id, @RequestParam("file") MultipartFile file) {
        DesktopVersion version = service.get(id);
        DesktopVersionStorage.StoredFile stored = storage.store(version.getPlatform(), version.getVersion(), file);
        return ApiResponse.ok(
                VersionDtos.VersionResponse.from(service.attachPackage(id, stored)),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    @PatchMapping("/api/admin/desktop-versions/{id}/published")
    ApiResponse<VersionDtos.VersionResponse> setPublished(
            @PathVariable String id,
            @RequestBody VersionDtos.PublishRequest request
    ) {
        return ApiResponse.ok(
                VersionDtos.VersionResponse.from(service.setPublished(id, request.published())),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    @GetMapping("/api/desktop/versions/check")
    ApiResponse<VersionDtos.UpdateCheckResponse> check(
            @RequestParam String platform,
            @RequestParam String currentVersion
    ) {
        return ApiResponse.ok(
                service.findUpdate(platform, currentVersion)
                        .map(VersionDtos.UpdateCheckResponse::available)
                        .orElseGet(VersionDtos.UpdateCheckResponse::none),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }
}
