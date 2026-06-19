package com.onehot.aidrama.system;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface SystemTaskRepository extends MongoRepository<SystemTask, String> {
}
