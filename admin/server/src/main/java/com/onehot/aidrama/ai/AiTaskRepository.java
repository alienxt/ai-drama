package com.onehot.aidrama.ai;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface AiTaskRepository extends MongoRepository<AiTask, String> {
}
