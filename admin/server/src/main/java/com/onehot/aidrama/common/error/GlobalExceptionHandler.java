package com.onehot.aidrama.common.error;

import com.onehot.aidrama.common.ApiError;
import com.onehot.aidrama.common.ApiResponse;
import com.onehot.aidrama.common.TraceIdFilter;
import com.onehot.aidrama.logs.ApplicationExceptionLogger;
import com.onehot.aidrama.logs.LogRequestContext;
import jakarta.servlet.http.HttpServletRequest;
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.Map;
import java.util.stream.Collectors;

@RestControllerAdvice
public class GlobalExceptionHandler {
    private final ApplicationExceptionLogger exceptionLogger;

    public GlobalExceptionHandler(ApplicationExceptionLogger exceptionLogger) {
        this.exceptionLogger = exceptionLogger;
    }

    @ExceptionHandler(BusinessException.class)
    ResponseEntity<ApiResponse<Void>> handleBusiness(BusinessException exception, HttpServletRequest request) {
        return error(exception.status(), exception.code(), exception.getMessage(), Map.of(), exception, request);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiResponse<Void>> handleValidation(MethodArgumentNotValidException exception, HttpServletRequest request) {
        Map<String, Object> details = exception.getBindingResult().getFieldErrors().stream()
                .collect(Collectors.toMap(FieldError::getField, FieldError::getDefaultMessage, (left, right) -> left));
        return error(HttpStatus.BAD_REQUEST, "VALIDATION_ERROR", "参数错误", details, exception, request);
    }

    @ExceptionHandler(AuthenticationException.class)
    ResponseEntity<ApiResponse<Void>> handleAuthentication(AuthenticationException exception, HttpServletRequest request) {
        return error(HttpStatus.UNAUTHORIZED, "UNAUTHORIZED", "请先登录", Map.of(), exception, request);
    }

    @ExceptionHandler(AccessDeniedException.class)
    ResponseEntity<ApiResponse<Void>> handleAccessDenied(AccessDeniedException exception, HttpServletRequest request) {
        return error(HttpStatus.FORBIDDEN, "FORBIDDEN", "没有权限执行该操作", Map.of(), exception, request);
    }

    @ExceptionHandler(Exception.class)
    ResponseEntity<ApiResponse<Void>> handleUnhandled(Exception exception, HttpServletRequest request) {
        return error(HttpStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR", "系统异常", Map.of(), exception, request);
    }

    private ResponseEntity<ApiResponse<Void>> error(
            HttpStatus status,
            String code,
            String message,
            Map<String, Object> details,
            Exception exception,
            HttpServletRequest request
    ) {
        String traceId = MDC.get(TraceIdFilter.TRACE_ID);
        writeExceptionLog(status, code, message, exception, request, traceId);
        return ResponseEntity.status(status).body(ApiResponse.failed(new ApiError(code, message, details), traceId));
    }

    private void writeExceptionLog(
            HttpStatus status,
            String code,
            String message,
            Exception exception,
            HttpServletRequest request,
            String traceId
    ) {
        LogRequestContext.Principal principal = LogRequestContext.principal();
        exceptionLogger.write(new ApplicationExceptionLogger.ApplicationExceptionInput(
                traceId,
                "HTTP",
                request.getMethod(),
                request.getRequestURI(),
                status.value(),
                code,
                message,
                exception,
                principal.accountId(),
                principal.username(),
                LogRequestContext.clientIp(request),
                LogRequestContext.userAgent(request)
        ));
    }
}
