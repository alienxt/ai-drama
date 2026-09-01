package com.onehot.aidrama.distribution;

import com.onehot.aidrama.configs.SystemConfigService;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class DistributionTaskMaintenanceServiceTest {
    @Test
    void stopsStaleActiveTasksBeforeUpload() {
        DistributionTaskRepository repository = mock(DistributionTaskRepository.class);
        SystemConfigService configService = mock(SystemConfigService.class);
        DistributionTaskMaintenanceService service = new DistributionTaskMaintenanceService(repository, configService);
        DistributionTask stale = new DistributionTask();
        stale.setStatus(DistributionTaskStatus.PROCESSING);
        stale.setLockedByDeviceId("device-1");
        stale.setUpdatedAt(Instant.now().minusSeconds(120));
        when(configService.get("distribution.activeTaskTimeoutMs")).thenReturn(Optional.of("60000"));
        when(repository.findByStatusInAndUpdatedAtBefore(any(), any())).thenReturn(List.of(stale));

        service.stopStaleActiveTasks();

        assertThat(stale.getStatus()).isEqualTo(DistributionTaskStatus.CANCELLED);
        assertThat(stale.getLockedByDeviceId()).isNull();
        assertThat(stale.getFailureReason()).contains("自动停止");
        assertThat(stale.getFinishedAt()).isNotNull();
        verify(repository).findByStatusInAndUpdatedAtBefore(argThat(statuses ->
                statuses.contains(DistributionTaskStatus.CLAIMED)
                        && statuses.contains(DistributionTaskStatus.DOWNLOADING)
                        && statuses.contains(DistributionTaskStatus.PROCESSING)
                        && !statuses.contains(DistributionTaskStatus.UPLOADING)
        ), any());
        verify(repository).save(stale);
    }
}
