package com.onehot.aidrama.dramas;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

class DramaRatingBackfillTest {
    @Test
    void setsMissingRatingsToFive() {
        MongoTemplate mongoTemplate = mock(MongoTemplate.class);

        new DramaRatingBackfill(mongoTemplate).backfillMissingRatings();

        ArgumentCaptor<Query> query = ArgumentCaptor.forClass(Query.class);
        ArgumentCaptor<Update> update = ArgumentCaptor.forClass(Update.class);
        verify(mongoTemplate).updateMulti(query.capture(), update.capture(), eq(Drama.class));
        assertThat(query.getValue().getQueryObject().toJson()).contains("rating");
        assertThat(query.getValue().getQueryObject().toJson()).contains("$exists");
        assertThat(update.getValue().getUpdateObject().toJson()).contains("\"rating\": 5");
    }
}
