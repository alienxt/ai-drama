package com.onehot.aidrama.common.config;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Bean;
import org.springframework.data.mongodb.config.EnableMongoAuditing;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;
import org.springframework.data.mongodb.core.index.IndexInfo;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

import static org.springframework.data.domain.Sort.Direction.ASC;
import static org.springframework.data.domain.Sort.Direction.DESC;

@Configuration
@EnableMongoAuditing
public class MongoConfig {
    @Bean
    ApplicationRunner ensureMongoIndexes(MongoTemplate mongoTemplate) {
        return args -> {
            mongoTemplate.indexOps("dramas")
                .ensureIndex(new Index()
                        .on("status", ASC)
                        .on("updatedAt", DESC)
                        .named("drama_status_updated_at_idx"));
            var contractTemplateIndexes = mongoTemplate.indexOps("contract_templates");
            mongoTemplate.updateMulti(
                    new Query(Criteria.where("platform").exists(false)),
                    new Update().set("platform", "WECHAT_VIDEO"),
                    "contract_templates"
            );
            contractTemplateIndexes.getIndexInfo().stream()
                    .filter(IndexInfo::isUnique)
                    .filter(index -> index.getIndexFields().size() == 1)
                    .filter(index -> "type".equals(index.getIndexFields().get(0).getKey()))
                    .forEach(index -> contractTemplateIndexes.dropIndex(index.getName()));
            contractTemplateIndexes.ensureIndex(new Index()
                    .on("platform", ASC)
                    .on("type", ASC)
                    .on("uploadedAt", DESC)
                    .named("contract_template_platform_type_uploaded_at_idx"));
        };
    }
}
