package com.onehot.aidrama.common;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;

public class MongoPageQuery {
    private final List<Criteria> criteria = new ArrayList<>();

    public MongoPageQuery containsAny(String keyword, String... fields) {
        if (keyword == null || keyword.isBlank()) {
            return this;
        }
        Pattern pattern = Pattern.compile(Pattern.quote(keyword.trim()), Pattern.CASE_INSENSITIVE);
        List<Criteria> alternatives = java.util.Arrays.stream(fields)
                .map(field -> Criteria.where(field).regex(pattern))
                .toList();
        criteria.add(new Criteria().orOperator(alternatives));
        return this;
    }

    public MongoPageQuery eq(String field, Object value) {
        if (value != null && (!(value instanceof String text) || !text.isBlank())) {
            criteria.add(Criteria.where(field).is(value));
        }
        return this;
    }

    public MongoPageQuery in(String field, List<String> values) {
        if (values != null && !values.isEmpty()) {
            criteria.add(Criteria.where(field).in(values));
        }
        return this;
    }

    public MongoPageQuery missingText(String field) {
        criteria.add(new Criteria().orOperator(
                Criteria.where(field).exists(false),
                Criteria.where(field).is(null),
                Criteria.where(field).is("")
        ));
        return this;
    }

    public MongoPageQuery hasText(String field) {
        criteria.add(Criteria.where(field).exists(true).nin(null, ""));
        return this;
    }

    public MongoPageQuery arraySize(String field, Integer size) {
        if (size != null && size > 0) {
            criteria.add(Criteria.where(field).size(size));
        }
        return this;
    }

    public MongoPageQuery range(String field, Object from, Object to) {
        if (from == null && to == null) {
            return this;
        }
        Criteria criterion = Criteria.where(field);
        if (from != null) {
            criterion = criterion.gte(from);
        }
        if (to != null) {
            criterion = criterion.lte(to);
        }
        criteria.add(criterion);
        return this;
    }

    public <T> Page<T> page(MongoTemplate mongoTemplate, Class<T> type, Pageable pageable) {
        Query query = toQuery();
        long total = mongoTemplate.count(query, type);
        List<T> content = mongoTemplate.find(query.with(pageable), type);
        return new PageImpl<>(content, pageable, total);
    }

    public Query toQuery() {
        Query query = new Query();
        if (!criteria.isEmpty()) {
            query.addCriteria(new Criteria().andOperator(criteria));
        }
        return query;
    }
}
