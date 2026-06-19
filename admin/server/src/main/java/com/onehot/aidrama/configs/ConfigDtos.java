package com.onehot.aidrama.configs;

public class ConfigDtos {
    public record ConfigRequest(String value, boolean secret) {
    }

    public record ConfigResponse(String key, String value, boolean secret) {
        static ConfigResponse from(SystemConfig config) {
            return new ConfigResponse(config.getKey(), config.isSecret() ? "******" : config.getValue(), config.isSecret());
        }
    }
}

