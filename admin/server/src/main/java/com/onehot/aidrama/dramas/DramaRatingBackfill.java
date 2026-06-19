package com.onehot.aidrama.dramas;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Component;

@Component
public class DramaRatingBackfill {
    private final MongoTemplate mongoTemplate;

    public DramaRatingBackfill(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public void backfillMissingRatings() {
        Query missingRating = Query.query(Criteria.where("rating").exists(false));
        Update defaultRating = new Update().set("rating", 5);
        mongoTemplate.updateMulti(missingRating, defaultRating, Drama.class);
    }
}
