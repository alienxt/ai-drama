package com.onehot.aidrama.logs;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.time.Instant;

@Service
public class LogWriter {
    private static final Logger log = LoggerFactory.getLogger(LogWriter.class);

    private final RequestLogRepository requestLogRepository;
    private final ExceptionLogRepository exceptionLogRepository;

    public LogWriter(RequestLogRepository requestLogRepository, ExceptionLogRepository exceptionLogRepository) {
        this.requestLogRepository = requestLogRepository;
        this.exceptionLogRepository = exceptionLogRepository;
    }

    public void writeRequest(RequestLogInput input) {
        try {
            RequestLog entry = new RequestLog();
            entry.setTraceId(input.traceId());
            entry.setMethod(input.method());
            entry.setPath(input.path());
            entry.setQuery(input.query());
            entry.setStatus(input.status());
            entry.setDurationMs(input.durationMs());
            entry.setAccountId(input.accountId());
            entry.setUsername(input.username());
            entry.setClientIp(input.clientIp());
            entry.setUserAgent(input.userAgent());
            entry.setCreatedAt(input.createdAt());
            requestLogRepository.save(entry);
        } catch (Exception exception) {
            log.warn("failed to write request log", exception);
        }
    }

    public void writeException(ExceptionLogInput input) {
        try {
            ExceptionLog entry = new ExceptionLog();
            entry.setTraceId(input.traceId());
            entry.setSource(input.source());
            entry.setMethod(input.method());
            entry.setPath(input.path());
            entry.setStatus(input.status());
            entry.setCode(input.code());
            entry.setMessage(input.message());
            entry.setExceptionClass(input.exceptionClass());
            entry.setStackTrace(input.stackTrace());
            entry.setAccountId(input.accountId());
            entry.setUsername(input.username());
            entry.setClientIp(input.clientIp());
            entry.setUserAgent(input.userAgent());
            entry.setCreatedAt(input.createdAt());
            exceptionLogRepository.save(entry);
        } catch (Exception exception) {
            log.warn("failed to write exception log", exception);
        }
    }

    public record RequestLogInput(
            String traceId,
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
    }

    public record ExceptionLogInput(
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
    }
}
