package com.onehot.aidrama.ai;

import com.onehot.aidrama.configs.SystemConfigService;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.Instant;

@Service
public class AiTaskMaintenanceService {
    private static final long DEFAULT_READ_TIMEOUT_SECONDS = 300;
    private static final long STALE_BUFFER_SECONDS = 60;

    private final AiTaskRepository repository;
    private final SystemConfigService configService;

    public AiTaskMaintenanceService(AiTaskRepository repository, SystemConfigService configService) {
        this.repository = repository;
        this.configService = configService;
    }

    @Scheduled(fixedDelayString = "${aidrama.ai.task-maintenance-fixed-delay-ms:60000}", initialDelayString = "${aidrama.ai.task-maintenance-initial-delay-ms:30000}")
    public void failStaleRunningTasks() {
        Instant now = Instant.now();
        Instant cutoff = now.minusSeconds(readTimeoutSeconds() + STALE_BUFFER_SECONDS);
        repository.findByStatusAndStartedAtBefore(AiTaskStatus.RUNNING, cutoff).forEach(task -> fail(task, now));
    }

    private void fail(AiTask task, Instant now) {
        task.setStatus(AiTaskStatus.FAILED);
        task.setFinishedAt(now);
        task.setErrorMessage("AI 任务超时或服务重启中断，已自动标记失败");
        if (task.getStartedAt() != null) {
            task.setDurationMs(Duration.between(task.getStartedAt(), now).toMillis());
        }
        repository.save(task);
    }

    private long readTimeoutSeconds() {
        return configService.get("openai.readTimeoutSeconds")
                .filter(value -> !value.isBlank())
                .map(value -> {
                    try {
                        return Long.parseLong(value.trim());
                    } catch (NumberFormatException exception) {
                        return DEFAULT_READ_TIMEOUT_SECONDS;
                    }
                })
                .orElse(DEFAULT_READ_TIMEOUT_SECONDS);
    }
}
