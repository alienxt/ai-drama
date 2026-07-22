package com.onehot.aidrama.distribution;

import com.onehot.aidrama.common.ApiResponse;
import com.onehot.aidrama.common.PageResult;
import com.onehot.aidrama.common.TraceIdFilter;
import com.onehot.aidrama.common.error.BusinessException;
import com.onehot.aidrama.common.security.JwtPrincipal;
import org.slf4j.MDC;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.List;

@RestController
public class DistributionTaskController {
    private final DistributionTaskRepository repository;
    private final DistributionService service;

    public DistributionTaskController(DistributionTaskRepository repository, DistributionService service) {
        this.repository = repository;
        this.service = service;
    }

    @GetMapping("/api/admin/distribution-tasks")
    ApiResponse<PageResult<DistributionDtos.AdminTaskResponse>> list(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) DistributionTaskStatus status,
            Pageable pageable
    ) {
        return ApiResponse.ok(service.listAdminTasks(keyword, status, pageable), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @GetMapping("/api/admin/distribution-tasks/stats")
    ApiResponse<List<DistributionDtos.TaskStatusCount>> stats(@RequestParam(required = false) String keyword) {
        return ApiResponse.ok(service.adminTaskStatusCounts(keyword), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PostMapping("/api/admin/distribution-tasks/generate")
    ApiResponse<List<DistributionTask>> generate() {
        return ApiResponse.ok(service.generateTasks(), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PostMapping("/api/desktop/devices/heartbeat")
    ApiResponse<Void> heartbeat(@RequestBody DistributionDtos.HeartbeatRequest request) {
        return ApiResponse.ok(null, MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PostMapping("/api/desktop/tasks/claim")
    ApiResponse<DistributionTask> claim(
            @AuthenticationPrincipal JwtPrincipal principal,
            @RequestBody DistributionDtos.ClaimRequest request
    ) {
        return ApiResponse.ok(
                service.claimForOwner(principal.accountId(), request.deviceId(), request.useAsyncPreparation()).orElse(null),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    @PostMapping("/api/desktop/tasks/publish-next")
    ApiResponse<DistributionTask> publishNext(
            @AuthenticationPrincipal JwtPrincipal principal,
            @RequestBody DistributionDtos.ClaimRequest request
    ) {
        return ApiResponse.ok(
                service.prepareAndClaimForOwner(principal.accountId(), request.deviceId(), request.useAsyncPreparation()).orElse(null),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    @GetMapping("/api/desktop/tasks")
    ApiResponse<PageResult<DistributionDtos.AdminTaskResponse>> listDesktopTasks(
            @AuthenticationPrincipal JwtPrincipal principal,
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) DistributionTaskStatus status,
            Pageable pageable
    ) {
        return ApiResponse.ok(
                service.listDesktopTasks(principal.accountId(), keyword, status, pageable),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    @PostMapping("/api/desktop/tasks/{id}/retry")
    ApiResponse<DistributionTask> retryDesktopTask(
            @AuthenticationPrincipal JwtPrincipal principal,
            @PathVariable String id,
            @RequestBody DistributionDtos.ClaimRequest request
    ) {
        return ApiResponse.ok(
                service.retryAndClaimForOwner(principal.accountId(), id, request.deviceId(), request.useAsyncPreparation()),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    @PostMapping("/api/desktop/tasks/{id}/prepare")
    ApiResponse<DistributionDtos.PreparationResponse> prepareDesktopTask(
            @AuthenticationPrincipal JwtPrincipal principal,
            @PathVariable String id
    ) {
        return ApiResponse.ok(
                service.prepareTaskDramaForOwner(principal.accountId(), id),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    @PostMapping("/api/desktop/tasks/{id}/pause")
    ApiResponse<DistributionTask> pauseDesktopTask(
            @AuthenticationPrincipal JwtPrincipal principal,
            @PathVariable String id,
            @RequestBody DistributionDtos.ClaimRequest request
    ) {
        return ApiResponse.ok(
                service.releaseTaskForOwner(principal.accountId(), id),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    @PostMapping("/api/desktop/tasks/{id}/skip")
    ApiResponse<DistributionTask> skipDesktopTask(
            @AuthenticationPrincipal JwtPrincipal principal,
            @PathVariable String id,
            @RequestBody DistributionDtos.ClaimRequest request
    ) {
        return ApiResponse.ok(
                service.releaseTaskForOwner(principal.accountId(), id),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    @PostMapping("/api/desktop/tasks/{id}/force-stop")
    ApiResponse<DistributionTask> forceStopDesktopTask(
            @AuthenticationPrincipal JwtPrincipal principal,
            @PathVariable String id
    ) {
        return ApiResponse.ok(
                service.forceStopTaskForOwner(principal.accountId(), id),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    @PostMapping("/api/desktop/dramas/{dramaId}/prioritize")
    ApiResponse<DistributionTask> prioritize(
            @AuthenticationPrincipal JwtPrincipal principal,
            @PathVariable String dramaId
    ) {
        return ApiResponse.ok(
                service.prioritizeDramaForOwner(principal.accountId(), dramaId),
                MDC.get(TraceIdFilter.TRACE_ID)
        );
    }

    @PutMapping("/api/desktop/tasks/{id}/progress")
    ApiResponse<DistributionTask> progress(@PathVariable String id, @RequestBody DistributionDtos.ProgressRequest request) {
        DistributionTask task = get(id);
        if (task.getStatus() == DistributionTaskStatus.CANCELLED) {
            return ApiResponse.ok(task, MDC.get(TraceIdFilter.TRACE_ID));
        }
        task.setStatus(request.status());
        task.setProgress(request.progress());
        return ApiResponse.ok(repository.save(task), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PutMapping("/api/desktop/tasks/{id}/result")
    ApiResponse<DistributionTask> result(@PathVariable String id, @RequestBody DistributionDtos.ResultRequest request) {
        DistributionTask task = get(id);
        if (task.getStatus() == DistributionTaskStatus.CANCELLED) {
            return ApiResponse.ok(task, MDC.get(TraceIdFilter.TRACE_ID));
        }
        Instant now = Instant.now();
        task.setStatus(request.success() ? DistributionTaskStatus.SUCCEEDED : DistributionTaskStatus.FAILED);
        task.setProgress(request.success() ? 100 : task.getProgress());
        task.setPlatformPublishId(request.platformPublishId());
        task.setPlatformSubmittedAt(request.success() || Boolean.TRUE.equals(request.platformSubmitted()) ? now : null);
        task.setFailureReason(request.failureReason());
        task.setFinishedAt(now);
        return ApiResponse.ok(repository.save(task), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PostMapping("/api/admin/distribution-tasks/{id}/retry")
    ApiResponse<DistributionTask> retry(@PathVariable String id) {
        return ApiResponse.ok(service.retryTaskFromAdmin(id), MDC.get(TraceIdFilter.TRACE_ID));
    }

    @PostMapping("/api/admin/distribution-tasks/{id}/cancel")
    ApiResponse<DistributionTask> cancel(@PathVariable String id) {
        DistributionTask task = get(id);
        task.setStatus(DistributionTaskStatus.CANCELLED);
        task.setFinishedAt(Instant.now());
        return ApiResponse.ok(repository.save(task), MDC.get(TraceIdFilter.TRACE_ID));
    }

    private DistributionTask get(String id) {
        return repository.findById(id)
                .orElseThrow(() -> new BusinessException("TASK_NOT_FOUND", "任务不存在", HttpStatus.NOT_FOUND));
    }
}
