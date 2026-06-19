package com.onehot.aidrama.configs;

import org.springframework.stereotype.Service;

import java.util.Optional;

@Service
public class SystemConfigService {
    private final SystemConfigRepository repository;

    public SystemConfigService(SystemConfigRepository repository) {
        this.repository = repository;
    }

    public Optional<String> get(String key) {
        return repository.findByKey(key).map(SystemConfig::getValue);
    }

    public String require(String key) {
        return get(key).orElseThrow(() -> new IllegalStateException("Missing system config: " + key));
    }

    public SystemConfig putIfAbsent(String key, String value, boolean secret) {
        return repository.findByKey(key).orElseGet(() -> {
            SystemConfig config = new SystemConfig();
            config.setKey(key);
            config.setValue(value);
            config.setSecret(secret);
            return repository.save(config);
        });
    }

    public SystemConfig put(String key, String value, boolean secret) {
        SystemConfig config = repository.findByKey(key).orElseGet(SystemConfig::new);
        config.setKey(key);
        config.setValue(value);
        config.setSecret(secret);
        return repository.save(config);
    }
}

