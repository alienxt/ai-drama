package com.onehot.aidrama.system;

import org.springframework.data.mongodb.repository.MongoRepository;

import java.time.Instant;
import java.util.List;

public interface SystemTaskRepository extends MongoRepository<SystemTask, String> {
    List<SystemTask> findByStatusAndStartedAtBefore(SystemTaskStatus status, Instant startedAt);
}
