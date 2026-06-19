package com.onehot.aidrama.logs;

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

class LogQueryTest {
    @Test
    void buildsSharedFiltersForRequestLogs() {
        MongoTemplate mongoTemplate = mock(MongoTemplate.class);
        when(mongoTemplate.find(org.mockito.ArgumentMatchers.any(Query.class), eq(RequestLog.class))).thenReturn(List.of());

        new LogQuery()
                .keyword("admin")
                .method("GET")
                .status(200)
                .traceId("trace-1")
                .username("root")
                .createdBetween(Instant.parse("2026-06-19T00:00:00Z"), Instant.parse("2026-06-20T00:00:00Z"))
                .page(mongoTemplate, RequestLog.class, PageRequest.of(0, 20));

        ArgumentCaptor<Query> query = ArgumentCaptor.forClass(Query.class);
        verify(mongoTemplate).count(query.capture(), eq(RequestLog.class));
        String queryText = query.getValue().getQueryObject().toString();
        assertThat(queryText).contains("admin");
        assertThat(queryText).contains("method");
        assertThat(queryText).contains("GET");
        assertThat(queryText).contains("status");
        assertThat(queryText).contains("trace-1");
        assertThat(queryText).contains("root");
        assertThat(queryText).contains("createdAt");
    }

    @Test
    void appliesNewestFirstSortWhenPageableIsUnsorted() {
        MongoTemplate mongoTemplate = mock(MongoTemplate.class);
        when(mongoTemplate.find(org.mockito.ArgumentMatchers.any(Query.class), eq(ExceptionLog.class))).thenReturn(List.of());

        new LogQuery().page(mongoTemplate, ExceptionLog.class, PageRequest.of(0, 20));

        ArgumentCaptor<Query> query = ArgumentCaptor.forClass(Query.class);
        verify(mongoTemplate).find(query.capture(), eq(ExceptionLog.class));
        assertThat(query.getValue().getSortObject().toString()).contains("createdAt=-1");
    }
}
