package com.onehot.aidrama.contracts;

import org.springframework.data.mongodb.repository.MongoRepository;

import java.util.List;

public interface ContractTemplateRepository extends MongoRepository<ContractTemplate, String> {
    List<ContractTemplate> findByTypeOrderByUploadedAtDesc(ContractTemplateType type);
}
