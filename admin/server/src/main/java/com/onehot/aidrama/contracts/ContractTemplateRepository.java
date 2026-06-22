package com.onehot.aidrama.contracts;

import com.onehot.aidrama.media.MediaPlatform;
import org.springframework.data.mongodb.repository.MongoRepository;

import java.util.List;

public interface ContractTemplateRepository extends MongoRepository<ContractTemplate, String> {
    List<ContractTemplate> findByPlatformAndTypeOrderByUploadedAtDesc(MediaPlatform platform, ContractTemplateType type);
}
