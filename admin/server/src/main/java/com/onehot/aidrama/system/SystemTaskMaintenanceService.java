package com.onehot.aidrama.system;

import com.onehot.aidrama.configs.SystemConfigService;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.Instant;

@Service
public class SystemTaskMaintenanceService {
    private static final long DEFAULT_TASK_TIMEOUT_MS = 30 * 60 * 1000L;

    private final SystemTaskRepository repository;
    private final SystemConfigService configService;

    public SystemTaskMaintenanceService(SystemTaskRepository repository, SystemConfigService configService) {
        this.repository = repository;
        this.configService = configService;
    }

    @Scheduled(fixedDelayString = "${aidrama.system.task-maintenance-fixed-delay-ms:60000}", initialDelayString = "${aidrama.system.task-maintenance-initial-delay-ms:30000}")
    public void failStaleRunningTasks() {
        Instant now = Instant.now();
        Instant cutoff = now.minusMillis(taskTimeoutMs());
        repository.findByStatusAndStartedAtBefore(SystemTaskStatus.RUNNING, cutoff).forEach(task -> fail(task, now));
    }

    private void fail(SystemTask task, Instant now) {
        task.setStatus(SystemTaskStatus.FAILED);
        task.setSummary("任务失败");
        task.setErrorMessage("系统任务超时或服务重启中断，已自动标记失败");
        task.setFinishedAt(now);
        if (task.getStartedAt() != null) {
            task.setDurationMs(Duration.between(task.getStartedAt(), now).toMillis());
        }
        repository.save(task);
    }

    private long taskTimeoutMs() {
        return configService.get("system.taskTimeoutMs")
                .filter(value -> !value.isBlank())
                .map(value -> {
                    try {
                        return Long.parseLong(value.trim());
                    } catch (NumberFormatException exception) {
                        return DEFAULT_TASK_TIMEOUT_MS;
                    }
                })
                .orElse(DEFAULT_TASK_TIMEOUT_MS);
    }
}
