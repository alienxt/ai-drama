package com.onehot.aidrama.logs;

import java.time.Instant;

public class LogDtos {
    private LogDtos() {
    }

    public record RequestLogResponse(
            String id,
            String traceId,
            String source,
            String method,
            String path,
            String query,
            int status,
            long durationMs,
            String accountId,
            String username,
            String clientIp,
            String userAgent,
            Instant createdAt
    ) {
        static RequestLogResponse from(RequestLog log) {
            return new RequestLogResponse(
                    log.getId(),
                    log.getTraceId(),
                    log.getSource(),
                    log.getMethod(),
                    log.getPath(),
                    log.getQuery(),
                    log.getStatus(),
                    log.getDurationMs(),
                    log.getAccountId(),
                    log.getUsername(),
                    log.getClientIp(),
                    log.getUserAgent(),
                    log.getCreatedAt()
            );
        }
    }

    public record ExceptionLogResponse(
            String id,
            String traceId,
            String source,
            String method,
            String path,
            int status,
            String code,
            String message,
            String exceptionClass,
            String stackTrace,
            String accountId,
            String username,
            String clientIp,
            String userAgent,
            Instant createdAt
    ) {
        static ExceptionLogResponse from(ExceptionLog log) {
            return new ExceptionLogResponse(
                    log.getId(),
                    log.getTraceId(),
                    log.getSource(),
                    log.getMethod(),
                    log.getPath(),
                    log.getStatus(),
                    log.getCode(),
                    log.getMessage(),
                    log.getExceptionClass(),
                    log.getStackTrace(),
                    log.getAccountId(),
                    log.getUsername(),
                    log.getClientIp(),
                    log.getUserAgent(),
                    log.getCreatedAt()
            );
        }
    }
}
