package com.onehot.aidrama.distribution;

import com.onehot.aidrama.configs.SystemConfigService;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.List;

@Service
public class DistributionTaskMaintenanceService {
    private static final long DEFAULT_ACTIVE_TASK_TIMEOUT_MS = 4 * 60 * 60 * 1000L;
    private static final long MIN_ACTIVE_TASK_TIMEOUT_MS = 10 * 60 * 1000L;
    private static final String TIMEOUT_FAILURE_REASON = "任务长时间无进度，已自动停止，可重试分发";
    private static final List<DistributionTaskStatus> STALE_STOPPABLE_STATUSES = List.of(
            DistributionTaskStatus.CLAIMED,
            DistributionTaskStatus.DOWNLOADING,
            DistributionTaskStatus.PROCESSING
    );

    private final DistributionTaskRepository repository;
    private final SystemConfigService configService;

    public DistributionTaskMaintenanceService(
            DistributionTaskRepository repository,
            SystemConfigService configService
    ) {
        this.repository = repository;
        this.configService = configService;
    }

    @Scheduled(
            fixedDelayString = "${aidrama.distribution.task-maintenance-fixed-delay-ms:60000}",
            initialDelayString = "${aidrama.distribution.task-maintenance-initial-delay-ms:30000}"
    )
    public void stopStaleActiveTasks() {
        Instant now = Instant.now();
        Instant cutoff = now.minusMillis(activeTaskTimeoutMs());
        repository.findByStatusInAndUpdatedAtBefore(STALE_STOPPABLE_STATUSES, cutoff)
                .forEach(task -> stop(task, now));
    }

    private void stop(DistributionTask task, Instant now) {
        task.setStatus(DistributionTaskStatus.CANCELLED);
        task.setLockedByDeviceId(null);
        task.setFailureReason(TIMEOUT_FAILURE_REASON);
        task.setFinishedAt(now);
        repository.save(task);
    }

    private long activeTaskTimeoutMs() {
        return configService.get("distribution.activeTaskTimeoutMs")
                .filter(value -> !value.isBlank())
                .map(value -> {
                    try {
                        long parsed = Long.parseLong(value.trim());
                        return parsed > 0 ? Math.max(MIN_ACTIVE_TASK_TIMEOUT_MS, parsed) : DEFAULT_ACTIVE_TASK_TIMEOUT_MS;
                    } catch (NumberFormatException exception) {
                        return DEFAULT_ACTIVE_TASK_TIMEOUT_MS;
                    }
                })
                .orElse(DEFAULT_ACTIVE_TASK_TIMEOUT_MS);
    }
}
