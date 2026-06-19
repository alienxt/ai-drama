package com.onehot.aidrama.ai;

import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.function.Function;
import java.util.function.Supplier;

@Service
public class AiTaskService {
    private final AiTaskRepository repository;

    public AiTaskService(AiTaskRepository repository) {
        this.repository = repository;
    }

    public <T> T run(AiTask task, Supplier<T> call, Function<T, Map<String, Object>> responsePayload) {
        Instant startedAt = Instant.now();
        task.setStartedAt(startedAt);
        task.setStatus(AiTaskStatus.RUNNING);
        AiTask saved = repository.save(task);
        try {
            T result = call.get();
            saved.setStatus(AiTaskStatus.SUCCEEDED);
            saved.setResponsePayload(responsePayload.apply(result));
            finish(saved, startedAt);
            return result;
        } catch (RuntimeException exception) {
            saved.setStatus(AiTaskStatus.FAILED);
            saved.setErrorMessage(exception.getMessage());
            finish(saved, startedAt);
            throw exception;
        }
    }

    private void finish(AiTask task, Instant startedAt) {
        Instant finishedAt = Instant.now();
        task.setFinishedAt(finishedAt);
        task.setDurationMs(Duration.between(startedAt, finishedAt).toMillis());
        repository.save(task);
    }
}
