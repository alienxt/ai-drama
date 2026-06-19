package com.onehot.aidrama.ai;

import org.springframework.data.mongodb.repository.MongoRepository;

import java.time.Instant;
import java.util.List;

public interface AiTaskRepository extends MongoRepository<AiTask, String> {
    List<AiTask> findByStatusAndStartedAtBefore(AiTaskStatus status, Instant startedAt);
}
