package com.onehot.aidrama.configs;

import java.util.Locale;

public class ConfigDtos {
    public record ConfigRequest(String value, boolean secret) {
    }

    public record ConfigResponse(String key, String value, boolean secret) {
        static ConfigResponse from(SystemConfig config) {
            boolean sensitive = config.isSecret() || sensitiveKey(config.getKey());
            return new ConfigResponse(config.getKey(), sensitive ? "******" : config.getValue(), sensitive);
        }

        private static boolean sensitiveKey(String key) {
            String lowerKey = key == null ? "" : key.toLowerCase(Locale.ROOT);
            return lowerKey.contains("password")
                    || lowerKey.contains("secret")
                    || lowerKey.contains("apikey")
                    || lowerKey.contains("api_key")
                    || lowerKey.contains("accesstoken")
                    || lowerKey.contains("access_token")
                    || lowerKey.contains("refreshtoken")
                    || lowerKey.contains("refresh_token")
                    || lowerKey.endsWith(".token");
        }
    }
}
