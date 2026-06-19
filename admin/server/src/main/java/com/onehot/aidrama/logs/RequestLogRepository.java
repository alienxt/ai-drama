package com.onehot.aidrama.logs;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface RequestLogRepository extends MongoRepository<RequestLog, String> {
}
