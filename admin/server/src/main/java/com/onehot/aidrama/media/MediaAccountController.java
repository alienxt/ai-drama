package com.onehot.aidrama.media;

import com.onehot.aidrama.common.ApiResponse;
import com.onehot.aidrama.common.error.BusinessException;
import com.onehot.aidrama.common.MongoPageQuery;
import com.onehot.aidrama.common.PageResult;
import com.onehot.aidrama.common.TraceIdFilter;
import com.onehot.aidrama.common.security.JwtPrincipal;
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.List;

@RestController
public class MediaAccountController {
    private final MediaAccountRepository repository;
    private final MongoTemplate mongoTemplate;

    public MediaAccountController(MediaAccountRepository repository, MongoTemplate mongoTemplate) {
        this.repository = repository;
        this.mongoTemplate = mongoTemplate;
    }

    @GetMapping("/api/admin/media-accounts")
    ApiResponse<PageResult<MediaAccount>> adminList(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) MediaPlatform platform,
            @RequestParam(required = false) MediaAccountStatus status,
            Pageable pageable
    ) {
        return ApiResponse.ok(PageResult.from(new MongoPageQuery()
                .containsAny(keyword, "displayName", "externalAccountId", "deviceId")
                .eq("platform", platform)
                .eq("status", status)
                .page(mongoTemplate, MediaAccount.class, pageable)), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @GetMapping("/api/desktop/media-accounts")
    ApiResponse<List<MediaAccount>> desktopList(@AuthenticationPrincipal JwtPrincipal principal) {
        return ApiResponse.ok(repository.findByOwnerAccountId(principal.accountId()), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PostMapping("/api/admin/media-accounts")
    ApiResponse<MediaAccount> adminCreate(@RequestBody MediaDtos.CreateMediaAccountRequest request) {
        MediaAccount account = new MediaAccount();
        account.setPlatform(request.platform());
        account.setDisplayName(request.displayName());
        account.setExternalAccountId(request.externalAccountId());
        account.setDeviceId(request.deviceId());
        return ApiResponse.ok(repository.save(account), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PostMapping("/api/desktop/media-accounts")
    ApiResponse<MediaAccount> create(@AuthenticationPrincipal JwtPrincipal principal, @RequestBody MediaDtos.CreateMediaAccountRequest request) {
        MediaAccount account = new MediaAccount();
        account.setOwnerAccountId(principal.accountId());
        account.setPlatform(request.platform());
        account.setDisplayName(request.displayName());
        account.setExternalAccountId(request.externalAccountId());
        account.setDeviceId(request.deviceId());
        return ApiResponse.ok(repository.save(account), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PutMapping("/api/desktop/media-accounts/{id}/login-state")
    ApiResponse<MediaAccount> updateLoginState(@AuthenticationPrincipal JwtPrincipal principal, @PathVariable String id, @RequestBody MediaDtos.LoginStateRequest request) {
        MediaAccount account = findOwned(principal, id);
        account.setLoginStateRef(request.loginStateRef());
        account.setDeviceId(request.deviceId());
        account.setLastVerifiedAt(Instant.now());
        account.setStatus(request.verified() ? MediaAccountStatus.ACTIVE : MediaAccountStatus.EXPIRED);
        return ApiResponse.ok(repository.save(account), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PatchMapping("/api/desktop/media-accounts/{id}/status")
    ApiResponse<MediaAccount> updateStatus(@AuthenticationPrincipal JwtPrincipal principal, @PathVariable String id, @RequestBody MediaDtos.StatusRequest request) {
        MediaAccount account = findOwned(principal, id);
        return ApiResponse.ok(saveDistributionStatus(account, request.status()), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PatchMapping("/api/admin/media-accounts/{id}/status")
    ApiResponse<MediaAccount> adminUpdateStatus(@PathVariable String id, @RequestBody MediaDtos.StatusRequest request) {
        MediaAccount account = repository.findById(id).orElseThrow();
        return ApiResponse.ok(saveDistributionStatus(account, request.status()), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PutMapping("/api/admin/media-accounts/{id}/policy")
    ApiResponse<MediaAccount> adminUpdatePolicy(@PathVariable String id, @RequestBody DistributionPolicy policy) {
        MediaAccount account = repository.findById(id).orElseThrow();
        account.setDistributionPolicy(policy);
        return ApiResponse.ok(repository.save(account), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @DeleteMapping("/api/admin/media-accounts/{id}")
    ApiResponse<Void> adminDelete(@PathVariable String id) {
        repository.deleteById(id);
        return ApiResponse.ok(null, MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PutMapping("/api/desktop/media-accounts/{id}/policy")
    ApiResponse<MediaAccount> updatePolicy(@AuthenticationPrincipal JwtPrincipal principal, @PathVariable String id, @RequestBody DistributionPolicy policy) {
        MediaAccount account = findOwned(principal, id);
        account.setDistributionPolicy(policy);
        return ApiResponse.ok(repository.save(account), MDC.get(TraceIdFilter.TRACE_ID));
    }

    private MediaAccount findOwned(JwtPrincipal principal, String id) {
        MediaAccount account = repository.findById(id).orElseThrow();
        if (!principal.accountId().equals(account.getOwnerAccountId())) {
            throw new BusinessException("MEDIA_NOT_FOUND", "媒体号不存在。", HttpStatus.NOT_FOUND);
        }
        return account;
    }

    private MediaAccount saveDistributionStatus(MediaAccount account, MediaAccountStatus status) {
        if (status != MediaAccountStatus.ACTIVE && status != MediaAccountStatus.PAUSED) {
            throw new BusinessException("INVALID_MEDIA_STATUS", "只能切换启用或暂停分发状态。", HttpStatus.BAD_REQUEST);
        }
        if (status == MediaAccountStatus.ACTIVE && (account.getLoginStateRef() == null || account.getLoginStateRef().isBlank())) {
            throw new BusinessException("MEDIA_LOGIN_REQUIRED", "启用前请先保存登录信息。", HttpStatus.BAD_REQUEST);
        }
        account.setStatus(status);
        return repository.save(account);
    }
}
