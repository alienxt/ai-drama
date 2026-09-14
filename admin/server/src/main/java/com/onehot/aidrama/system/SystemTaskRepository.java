package com.onehot.aidrama.system;

import org.springframework.data.mongodb.repository.MongoRepository;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

public interface SystemTaskRepository extends MongoRepository<SystemTask, String> {
    List<SystemTask> findByStatusAndStartedAtBefore(SystemTaskStatus status, Instant startedAt);

    Optional<SystemTask> findFirstByTypeOrderByStartedAtDesc(SystemTaskType type);
}
