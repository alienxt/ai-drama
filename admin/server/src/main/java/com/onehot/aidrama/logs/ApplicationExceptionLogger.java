package com.onehot.aidrama.logs;

import org.springframework.stereotype.Service;

import java.io.PrintWriter;
import java.io.StringWriter;
import java.time.Instant;

@Service
public class ApplicationExceptionLogger {
    private static final int STACK_TRACE_LIMIT = 4000;

    private final LogWriter logWriter;

    public ApplicationExceptionLogger(LogWriter logWriter) {
        this.logWriter = logWriter;
    }

    public void write(ApplicationExceptionInput input) {
        logWriter.writeException(new LogWriter.ExceptionLogInput(
                input.traceId(),
                input.source(),
                input.method(),
                input.path(),
                input.status(),
                input.code(),
                input.message(),
                input.exception().getClass().getName(),
                stackTracePreview(input.exception()),
                input.accountId(),
                input.username(),
                input.clientIp(),
                input.userAgent(),
                Instant.now()
        ));
    }

    private String stackTracePreview(Throwable exception) {
        StringWriter writer = new StringWriter();
        exception.printStackTrace(new PrintWriter(writer));
        String stackTrace = writer.toString();
        return stackTrace.length() <= STACK_TRACE_LIMIT ? stackTrace : stackTrace.substring(0, STACK_TRACE_LIMIT);
    }

    public record ApplicationExceptionInput(
            String traceId,
            String source,
            String method,
            String path,
            int status,
            String code,
            String message,
            Throwable exception,
            String accountId,
            String username,
            String clientIp,
            String userAgent
    ) {
    }
}
