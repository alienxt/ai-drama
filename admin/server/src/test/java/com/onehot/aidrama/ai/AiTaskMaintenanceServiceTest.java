package com.onehot.aidrama.ai;

import com.onehot.aidrama.configs.SystemConfigService;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AiTaskMaintenanceServiceTest {
    @Test
    void marksStaleRunningTasksAsFailed() {
        AiTaskRepository repository = mock(AiTaskRepository.class);
        SystemConfigService configService = mock(SystemConfigService.class);
        AiTaskMaintenanceService service = new AiTaskMaintenanceService(repository, configService);
        AiTask stale = new AiTask();
        stale.setStatus(AiTaskStatus.RUNNING);
        stale.setStartedAt(Instant.now().minusSeconds(500));
        when(configService.get("openai.readTimeoutSeconds")).thenReturn(Optional.of("300"));
        when(repository.findByStatusAndStartedAtBefore(any(), any())).thenReturn(List.of(stale));

        service.failStaleRunningTasks();

        assertThat(stale.getStatus()).isEqualTo(AiTaskStatus.FAILED);
        assertThat(stale.getErrorMessage()).contains("任务超时");
        assertThat(stale.getFinishedAt()).isNotNull();
        assertThat(stale.getDurationMs()).isNotNull();
        verify(repository).save(stale);
    }
}
