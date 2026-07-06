package com.onehot.aidrama.logs;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;

public class LogQuery {
    private final List<Criteria> criteria = new ArrayList<>();

    public LogQuery keyword(String keyword) {
        if (keyword == null || keyword.isBlank()) {
            return this;
        }
        Pattern pattern = Pattern.compile(Pattern.quote(keyword.trim()), Pattern.CASE_INSENSITIVE);
        criteria.add(new Criteria().orOperator(
                Criteria.where("traceId").regex(pattern),
                Criteria.where("source").regex(pattern),
                Criteria.where("method").regex(pattern),
                Criteria.where("path").regex(pattern),
                Criteria.where("query").regex(pattern),
                Criteria.where("endpoint").regex(pattern),
                Criteria.where("requestUrl").regex(pattern),
                Criteria.where("requestBody").regex(pattern),
                Criteria.where("responseBody").regex(pattern),
                Criteria.where("errorMessage").regex(pattern),
                Criteria.where("username").regex(pattern),
                Criteria.where("clientIp").regex(pattern),
                Criteria.where("userAgent").regex(pattern),
                Criteria.where("code").regex(pattern),
                Criteria.where("message").regex(pattern),
                Criteria.where("exceptionClass").regex(pattern)
        ));
        return this;
    }

    public LogQuery method(String method) {
        if (method != null && !method.isBlank()) {
            criteria.add(Criteria.where("method").is(method.trim().toUpperCase()));
        }
        return this;
    }

    public LogQuery status(Integer status) {
        if (status != null) {
            criteria.add(Criteria.where("status").is(status));
        }
        return this;
    }

    public LogQuery traceId(String traceId) {
        if (traceId != null && !traceId.isBlank()) {
            criteria.add(Criteria.where("traceId").is(traceId.trim()));
        }
        return this;
    }

    public LogQuery username(String username) {
        if (username != null && !username.isBlank()) {
            criteria.add(Criteria.where("username").is(username.trim()));
        }
        return this;
    }

    public LogQuery createdBetween(Instant from, Instant to) {
        if (from == null && to == null) {
            return this;
        }
        Criteria createdAt = Criteria.where("createdAt");
        if (from != null) {
            createdAt = createdAt.gte(from);
        }
        if (to != null) {
            createdAt = createdAt.lte(to);
        }
        criteria.add(createdAt);
        return this;
    }

    public <T> Page<T> page(MongoTemplate mongoTemplate, Class<T> type, Pageable pageable) {
        Query query = new Query();
        if (!criteria.isEmpty()) {
            query.addCriteria(new Criteria().andOperator(criteria));
        }
        long total = mongoTemplate.count(query, type);
        Pageable effectivePageable = pageable.getSort().isSorted()
                ? pageable
                : PageRequest.of(
                pageable.getPageNumber(),
                pageable.getPageSize(),
                Sort.by(Sort.Direction.DESC, "createdAt")
        );
        List<T> content = mongoTemplate.find(query.with(effectivePageable), type);
        return new PageImpl<>(content, effectivePageable, total);
    }
}
