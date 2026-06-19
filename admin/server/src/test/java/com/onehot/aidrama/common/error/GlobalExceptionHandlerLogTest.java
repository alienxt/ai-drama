package com.onehot.aidrama.common.error;

import com.onehot.aidrama.common.ApiResponse;
import com.onehot.aidrama.common.TraceIdFilter;
import com.onehot.aidrama.logs.ApplicationExceptionLogger;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.mock.web.MockHttpServletRequest;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

class GlobalExceptionHandlerLogTest {
    @Test
    void recordsExceptionLogAndPreservesErrorResponse() {
        ApplicationExceptionLogger logger = mock(ApplicationExceptionLogger.class);
        GlobalExceptionHandler handler = new GlobalExceptionHandler(logger);
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/admin/configs");
        request.addHeader("User-Agent", "JUnit");
        request.setRemoteAddr("127.0.0.1");
        MDC.put(TraceIdFilter.TRACE_ID, "trace-1");
        try {
            ResponseEntity<ApiResponse<Void>> response = handler.handleUnhandled(new IllegalStateException("boom"), request);

            assertThat(response.getStatusCode()).isEqualTo(HttpStatus.INTERNAL_SERVER_ERROR);
            assertThat(response.getBody()).isNotNull();
            assertThat(response.getBody().success()).isFalse();
            assertThat(response.getBody().error().code()).isEqualTo("INTERNAL_ERROR");
            ArgumentCaptor<ApplicationExceptionLogger.ApplicationExceptionInput> input =
                    ArgumentCaptor.forClass(ApplicationExceptionLogger.ApplicationExceptionInput.class);
            verify(logger).write(input.capture());
            assertThat(input.getValue().traceId()).isEqualTo("trace-1");
            assertThat(input.getValue().source()).isEqualTo("HTTP");
            assertThat(input.getValue().path()).isEqualTo("/api/admin/configs");
            assertThat(input.getValue().status()).isEqualTo(500);
            assertThat(input.getValue().code()).isEqualTo("INTERNAL_ERROR");
            assertThat(input.getValue().exception()).isInstanceOf(IllegalStateException.class);
        } finally {
            MDC.remove(TraceIdFilter.TRACE_ID);
        }
    }
}
