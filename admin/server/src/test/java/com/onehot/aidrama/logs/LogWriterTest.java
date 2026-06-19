package com.onehot.aidrama.logs;

import org.junit.jupiter.api.Test;

import java.time.Instant;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class LogWriterTest {
    @Test
    void writesRequestLogWithCapturedContext() {
        RequestLogRepository requestLogs = mock(RequestLogRepository.class);
        LogWriter writer = new LogWriter(requestLogs, mock(ExceptionLogRepository.class));
        LogWriter.RequestLogInput input = new LogWriter.RequestLogInput(
                "trace-1",
                "GET",
                "/api/admin/configs",
                "page=0",
                200,
                32,
                "account-1",
                "admin",
                "127.0.0.1",
                "JUnit",
                Instant.parse("2026-06-19T08:00:00Z")
        );

        writer.writeRequest(input);

        verify(requestLogs).save(org.mockito.ArgumentMatchers.argThat(log ->
                "trace-1".equals(log.getTraceId())
                        && "GET".equals(log.getMethod())
                        && "/api/admin/configs".equals(log.getPath())
                        && log.getStatus() == 200
                        && log.getDurationMs() == 32
                        && "admin".equals(log.getUsername())
        ));
    }

    @Test
    void writesExceptionLogWithCapturedContext() {
        ExceptionLogRepository exceptionLogs = mock(ExceptionLogRepository.class);
        LogWriter writer = new LogWriter(mock(RequestLogRepository.class), exceptionLogs);
        LogWriter.ExceptionLogInput input = new LogWriter.ExceptionLogInput(
                "trace-2",
                "HTTP",
                "POST",
                "/api/admin/configs",
                500,
                "INTERNAL_ERROR",
                "系统异常",
                IllegalStateException.class.getName(),
                "java.lang.IllegalStateException: boom",
                "account-1",
                "admin",
                "127.0.0.1",
                "JUnit",
                Instant.parse("2026-06-19T08:00:00Z")
        );

        writer.writeException(input);

        verify(exceptionLogs).save(org.mockito.ArgumentMatchers.argThat(log ->
                "trace-2".equals(log.getTraceId())
                        && "HTTP".equals(log.getSource())
                        && "INTERNAL_ERROR".equals(log.getCode())
                        && "系统异常".equals(log.getMessage())
                        && IllegalStateException.class.getName().equals(log.getExceptionClass())
        ));
    }

    @Test
    void swallowsPersistenceFailures() {
        RequestLogRepository requestLogs = mock(RequestLogRepository.class);
        when(requestLogs.save(any(RequestLog.class))).thenThrow(new IllegalStateException("mongo down"));
        LogWriter writer = new LogWriter(requestLogs, mock(ExceptionLogRepository.class));

        assertThatCode(() -> writer.writeRequest(new LogWriter.RequestLogInput(
                "trace-1",
                "GET",
                "/api/admin/configs",
                null,
                200,
                1,
                null,
                null,
                null,
                null,
                Instant.now()
        ))).doesNotThrowAnyException();
    }
}
