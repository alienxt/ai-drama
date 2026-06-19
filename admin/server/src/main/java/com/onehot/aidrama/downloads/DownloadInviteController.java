package com.onehot.aidrama.downloads;

import com.onehot.aidrama.common.ApiResponse;
import com.onehot.aidrama.common.PageResult;
import com.onehot.aidrama.common.TraceIdFilter;
import com.onehot.aidrama.versions.DesktopVersionService;
import org.slf4j.MDC;
import org.springframework.data.domain.Pageable;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DownloadInviteController {
    private final DownloadInviteRepository repository;
    private final DownloadInviteService service;
    private final DesktopVersionService versionService;

    public DownloadInviteController(
            DownloadInviteRepository repository,
            DownloadInviteService service,
            DesktopVersionService versionService
    ) {
        this.repository = repository;
        this.service = service;
        this.versionService = versionService;
    }

    @GetMapping("/api/admin/download-invites")
    ApiResponse<PageResult<DownloadInviteDtos.InviteResponse>> list(Pageable pageable) {
        return ApiResponse.ok(
                PageResult.from(repository.findAll(pageable).map(DownloadInviteDtos.InviteResponse::from)),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    @PostMapping("/api/admin/download-invites")
    ApiResponse<DownloadInviteDtos.InviteResponse> create(@RequestBody DownloadInviteDtos.InviteRequest request) {
        return ApiResponse.ok(
                DownloadInviteDtos.InviteResponse.from(service.create(request)),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    @PutMapping("/api/admin/download-invites/{id}")
    ApiResponse<DownloadInviteDtos.InviteResponse> update(
            @PathVariable String id,
            @RequestBody DownloadInviteDtos.InviteRequest request
    ) {
        return ApiResponse.ok(
                DownloadInviteDtos.InviteResponse.from(service.update(id, request)),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    @GetMapping("/api/public/desktop-versions/latest")
    ApiResponse<DownloadInviteDtos.PublicVersionResponse> latest(@RequestParam String platform) {
        String normalizedPlatform = versionService.normalizePlatform(platform);
        return ApiResponse.ok(
                versionService.findLatestPublished(platform)
                        .map(DownloadInviteDtos.PublicVersionResponse::from)
                        .orElseGet(() -> DownloadInviteDtos.PublicVersionResponse.none(normalizedPlatform)),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    @PostMapping("/api/public/download-invites/validate")
    ApiResponse<DownloadInviteDtos.DownloadAccessResponse> validate(
            @RequestBody DownloadInviteDtos.ValidateRequest request
    ) {
        return ApiResponse.ok(
                service.validate(request.code(), request.platform()),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }
}
