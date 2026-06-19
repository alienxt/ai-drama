package com.onehot.aidrama.logs;

import java.time.Instant;

public interface LogEntry {
    String getId();

    String getTraceId();

    String getMethod();

    String getPath();

    int getStatus();

    String getAccountId();

    String getUsername();

    String getClientIp();

    String getUserAgent();

    Instant getCreatedAt();
}
