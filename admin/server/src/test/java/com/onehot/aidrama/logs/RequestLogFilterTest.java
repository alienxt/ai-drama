package com.onehot.aidrama.logs;

import com.onehot.aidrama.common.TraceIdFilter;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.slf4j.MDC;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

class RequestLogFilterTest {
    @Test
    void writesRequestLogForApiRequest() throws Exception {
        LogWriter writer = mock(LogWriter.class);
        RequestLogFilter filter = new RequestLogFilter(writer);
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/admin/configs");
        request.setQueryString("page=0");
        request.addHeader("User-Agent", "JUnit");
        request.setRemoteAddr("127.0.0.1");
        MockHttpServletResponse response = new MockHttpServletResponse();
        MDC.put(TraceIdFilter.TRACE_ID, "trace-1");
        try {
            filter.doFilter(request, response, new MockFilterChain());
        } finally {
            MDC.remove(TraceIdFilter.TRACE_ID);
        }

        ArgumentCaptor<LogWriter.RequestLogInput> input = ArgumentCaptor.forClass(LogWriter.RequestLogInput.class);
        verify(writer).writeRequest(input.capture());
        assertThat(input.getValue().traceId()).isEqualTo("trace-1");
        assertThat(input.getValue().method()).isEqualTo("GET");
        assertThat(input.getValue().path()).isEqualTo("/api/admin/configs");
        assertThat(input.getValue().query()).isEqualTo("page=0");
        assertThat(input.getValue().status()).isEqualTo(200);
        assertThat(input.getValue().durationMs()).isGreaterThanOrEqualTo(0);
    }

    @Test
    void skipsLogApiRequests() throws Exception {
        LogWriter writer = mock(LogWriter.class);
        RequestLogFilter filter = new RequestLogFilter(writer);
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/admin/request-logs");

        filter.doFilter(request, new MockHttpServletResponse(), new MockFilterChain());

        verify(writer, never()).writeRequest(org.mockito.ArgumentMatchers.any());
    }
}
