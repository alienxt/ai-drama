package com.onehot.aidrama.common.config;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Bean;
import org.springframework.data.mongodb.config.EnableMongoAuditing;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;

import static org.springframework.data.domain.Sort.Direction.ASC;
import static org.springframework.data.domain.Sort.Direction.DESC;

@Configuration
@EnableMongoAuditing
public class MongoConfig {
    @Bean
    ApplicationRunner ensureMongoIndexes(MongoTemplate mongoTemplate) {
        return args -> mongoTemplate.indexOps("dramas")
                .ensureIndex(new Index()
                        .on("status", ASC)
                        .on("updatedAt", DESC)
                        .named("drama_status_updated_at_idx"));
    }
}
