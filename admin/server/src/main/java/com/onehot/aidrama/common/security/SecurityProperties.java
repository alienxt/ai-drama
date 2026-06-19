package com.onehot.aidrama.common.security;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "aidrama.security")
public record SecurityProperties(String jwtSecret, long tokenTtlMinutes) {
}

