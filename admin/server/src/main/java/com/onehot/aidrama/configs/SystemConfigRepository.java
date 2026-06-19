package com.onehot.aidrama.configs;

import org.springframework.data.mongodb.repository.MongoRepository;

import java.util.Optional;

public interface SystemConfigRepository extends MongoRepository<SystemConfig, String> {
    Optional<SystemConfig> findByKey(String key);
}

