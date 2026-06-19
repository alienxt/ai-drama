package com.onehot.aidrama.system;

import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.function.Function;
import java.util.function.Supplier;

@Service
public class SystemTaskService {
    private final SystemTaskRepository repository;

    public SystemTaskService(SystemTaskRepository repository) {
        this.repository = repository;
    }

    public <T> T run(
            SystemTaskType type,
            String title,
            String triggerSource,
            Map<String, Object> requestPayload,
            Supplier<T> work,
            Function<T, TaskResult> resultMapper
    ) {
        Instant startedAt = Instant.now();
        SystemTask task = new SystemTask();
        task.setType(type);
        task.setTitle(title);
        task.setTriggerSource(triggerSource);
        task.setRequestPayload(requestPayload);
        task.setStartedAt(startedAt);
        task.setStatus(SystemTaskStatus.RUNNING);
        SystemTask saved = repository.save(task);
        try {
            T result = work.get();
            TaskResult taskResult = resultMapper.apply(result);
            saved.setStatus(SystemTaskStatus.SUCCEEDED);
            saved.setSummary(taskResult.summary());
            saved.setResultPayload(taskResult.details());
            finish(saved, startedAt);
            return result;
        } catch (RuntimeException exception) {
            saved.setStatus(SystemTaskStatus.FAILED);
            saved.setErrorMessage(exception.getMessage());
            saved.setSummary("任务失败");
            finish(saved, startedAt);
            throw exception;
        }
    }

    private void finish(SystemTask task, Instant startedAt) {
        Instant finishedAt = Instant.now();
        task.setFinishedAt(finishedAt);
        task.setDurationMs(Duration.between(startedAt, finishedAt).toMillis());
        repository.save(task);
    }

    public record TaskResult(String summary, Map<String, Object> details) {
    }
}
