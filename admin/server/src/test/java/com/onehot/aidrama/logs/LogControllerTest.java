package com.onehot.aidrama.logs;

import com.onehot.aidrama.common.PageResult;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Query;

import java.time.Instant;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class LogControllerTest {
    @Test
    void listsRequestLogsWithSharedFilters() {
        MongoTemplate mongoTemplate = mock(MongoTemplate.class);
        RequestLog log = new RequestLog();
        log.setTraceId("trace-1");
        log.setMethod("GET");
        log.setPath("/api/admin/configs");
        log.setStatus(200);
        log.setCreatedAt(Instant.parse("2026-06-19T08:00:00Z"));
        when(mongoTemplate.count(org.mockito.ArgumentMatchers.any(Query.class), eq(RequestLog.class))).thenReturn(1L);
        when(mongoTemplate.find(org.mockito.ArgumentMatchers.any(Query.class), eq(RequestLog.class))).thenReturn(List.of(log));
        LogController controller = new LogController(mongoTemplate);

        PageResult<LogDtos.RequestLogResponse> result = controller.requestLogs(
                "configs",
                "GET",
                200,
                "trace-1",
                null,
                null,
                null,
                PageRequest.of(0, 10)
        ).data();

        assertThat(result.content()).hasSize(1);
        assertThat(result.content().getFirst().traceId()).isEqualTo("trace-1");
        ArgumentCaptor<Query> query = ArgumentCaptor.forClass(Query.class);
        verify(mongoTemplate).count(query.capture(), eq(RequestLog.class));
        assertThat(query.getValue().getQueryObject().toString()).contains("configs");
    }

    @Test
    void listsExceptionLogsWithMessageAndExceptionClass() {
        MongoTemplate mongoTemplate = mock(MongoTemplate.class);
        ExceptionLog log = new ExceptionLog();
        log.setTraceId("trace-2");
        log.setMethod("POST");
        log.setPath("/api/admin/configs");
        log.setStatus(500);
        log.setCode("INTERNAL_ERROR");
        log.setMessage("系统异常");
        log.setExceptionClass(IllegalStateException.class.getName());
        log.setCreatedAt(Instant.parse("2026-06-19T08:00:00Z"));
        when(mongoTemplate.count(org.mockito.ArgumentMatchers.any(Query.class), eq(ExceptionLog.class))).thenReturn(1L);
        when(mongoTemplate.find(org.mockito.ArgumentMatchers.any(Query.class), eq(ExceptionLog.class))).thenReturn(List.of(log));
        LogController controller = new LogController(mongoTemplate);

        PageResult<LogDtos.ExceptionLogResponse> result = controller.exceptionLogs(
                "系统异常",
                null,
                500,
                null,
                null,
                null,
                null,
                PageRequest.of(0, 10)
        ).data();

        assertThat(result.content()).hasSize(1);
        assertThat(result.content().getFirst().code()).isEqualTo("INTERNAL_ERROR");
        assertThat(result.content().getFirst().exceptionClass()).isEqualTo(IllegalStateException.class.getName());
    }
}
