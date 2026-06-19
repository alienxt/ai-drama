package com.onehot.aidrama.system;

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

class SystemTaskMaintenanceServiceTest {
    @Test
    void marksStaleRunningTasksAsFailed() {
        SystemTaskRepository repository = mock(SystemTaskRepository.class);
        SystemConfigService configService = mock(SystemConfigService.class);
        SystemTaskMaintenanceService service = new SystemTaskMaintenanceService(repository, configService);
        SystemTask stale = new SystemTask();
        stale.setStatus(SystemTaskStatus.RUNNING);
        stale.setStartedAt(Instant.now().minusSeconds(120));
        when(configService.get("system.taskTimeoutMs")).thenReturn(Optional.of("60000"));
        when(repository.findByStatusAndStartedAtBefore(any(), any())).thenReturn(List.of(stale));

        service.failStaleRunningTasks();

        assertThat(stale.getStatus()).isEqualTo(SystemTaskStatus.FAILED);
        assertThat(stale.getSummary()).isEqualTo("任务失败");
        assertThat(stale.getErrorMessage()).contains("服务重启中断");
        assertThat(stale.getFinishedAt()).isNotNull();
        assertThat(stale.getDurationMs()).isNotNull();
        verify(repository).save(stale);
    }
}
