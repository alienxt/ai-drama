package com.onehot.aidrama.logs;

import com.onehot.aidrama.common.TraceIdFilter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.time.Instant;

@Component
@Order(Ordered.LOWEST_PRECEDENCE)
public class RequestLogFilter extends OncePerRequestFilter {
    private final LogWriter logWriter;

    public RequestLogFilter(LogWriter logWriter) {
        this.logWriter = logWriter;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI();
        return !path.startsWith("/api/")
                || path.equals("/api/admin/request-logs")
                || path.equals("/api/admin/exception-logs");
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        long startedAt = System.nanoTime();
        try {
            filterChain.doFilter(request, response);
        } finally {
            long durationMs = Math.max(0, (System.nanoTime() - startedAt) / 1_000_000);
            LogRequestContext.Principal principal = LogRequestContext.principal();
            logWriter.writeRequest(new LogWriter.RequestLogInput(
                    MDC.get(TraceIdFilter.TRACE_ID),
                    request.getMethod(),
                    request.getRequestURI(),
                    request.getQueryString(),
                    response.getStatus(),
                    durationMs,
                    principal.accountId(),
                    principal.username(),
                    LogRequestContext.clientIp(request),
                    LogRequestContext.userAgent(request),
                    Instant.now()
            ));
        }
    }
}
