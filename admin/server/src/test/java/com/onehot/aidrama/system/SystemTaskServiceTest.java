package com.onehot.aidrama.system;

import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.doAnswer;

class SystemTaskServiceTest {
    @Test
    void recordsSuccessfulSystemTaskWithSummaryAndDetails() {
        List<SystemTask> saved = new ArrayList<>();
        SystemTaskRepository repository = repository(saved);
        SystemTaskService service = new SystemTaskService(repository);

        List<String> result = service.run(
                SystemTaskType.BAIDU_PAN_SCAN,
                "扫描百度网盘",
                "manual",
                Map.of("remoteRoot", "/drama/真人剧/2026"),
                () -> List.of("drama-1", "drama-2"),
                dramas -> new SystemTaskService.TaskResult(
                        "导入 2 部短剧",
                        Map.of("importedCount", dramas.size(), "dramaIds", dramas)
                )
        );

        assertThat(result).containsExactly("drama-1", "drama-2");
        assertThat(saved).hasSize(2);
        SystemTask started = saved.get(0);
        SystemTask finished = saved.get(1);
        assertThat(started.getStatus()).isEqualTo(SystemTaskStatus.RUNNING);
        assertThat(finished.getStatus()).isEqualTo(SystemTaskStatus.SUCCEEDED);
        assertThat(finished.getType()).isEqualTo(SystemTaskType.BAIDU_PAN_SCAN);
        assertThat(finished.getTitle()).isEqualTo("扫描百度网盘");
        assertThat(finished.getTriggerSource()).isEqualTo("manual");
        assertThat(finished.getSummary()).isEqualTo("导入 2 部短剧");
        assertThat(finished.getRequestPayload()).containsEntry("remoteRoot", "/drama/真人剧/2026");
        assertThat(finished.getResultPayload()).containsEntry("importedCount", 2);
        assertThat(finished.getDurationMs()).isNotNull();
        assertThat(finished.getFinishedAt()).isNotNull();
    }

    @Test
    void recordsFailedSystemTaskAndRethrowsException() {
        List<SystemTask> saved = new ArrayList<>();
        SystemTaskRepository repository = repository(saved);
        SystemTaskService service = new SystemTaskService(repository);

        assertThatThrownBy(() -> service.run(
                SystemTaskType.BAIDU_PAN_SCAN,
                "扫描百度网盘",
                "scheduled",
                Map.of(),
                () -> {
                    throw new IllegalStateException("scan failed");
                },
                ignored -> new SystemTaskService.TaskResult("won't happen", Map.of())
        )).isInstanceOf(IllegalStateException.class);

        SystemTask finished = saved.get(1);
        assertThat(finished.getStatus()).isEqualTo(SystemTaskStatus.FAILED);
        assertThat(finished.getErrorMessage()).isEqualTo("scan failed");
        assertThat(finished.getFinishedAt()).isNotNull();
    }

    private SystemTaskRepository repository(List<SystemTask> saved) {
        SystemTaskRepository repository = mock(SystemTaskRepository.class);
        doAnswer(invocation -> {
            SystemTask task = invocation.getArgument(0);
            saved.add(snapshot(task));
            return task;
        }).when(repository).save(any(SystemTask.class));
        return repository;
    }

    private SystemTask snapshot(SystemTask task) {
        SystemTask snapshot = new SystemTask();
        snapshot.setType(task.getType());
        snapshot.setStatus(task.getStatus());
        snapshot.setTitle(task.getTitle());
        snapshot.setTriggerSource(task.getTriggerSource());
        snapshot.setSummary(task.getSummary());
        snapshot.setRequestPayload(task.getRequestPayload());
        snapshot.setResultPayload(task.getResultPayload());
        snapshot.setErrorMessage(task.getErrorMessage());
        snapshot.setDurationMs(task.getDurationMs());
        snapshot.setStartedAt(task.getStartedAt());
        snapshot.setFinishedAt(task.getFinishedAt());
        return snapshot;
    }
}
