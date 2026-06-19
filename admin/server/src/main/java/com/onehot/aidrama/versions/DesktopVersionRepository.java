package com.onehot.aidrama.versions;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.repository.MongoRepository;

import java.util.List;

public interface DesktopVersionRepository extends MongoRepository<DesktopVersion, String> {
    List<DesktopVersion> findByPlatformAndPublished(String platform, boolean published, Sort sort);
}

