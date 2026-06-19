package com.onehot.aidrama.downloads;

import org.springframework.data.mongodb.repository.MongoRepository;

import java.util.Optional;

public interface DownloadInviteRepository extends MongoRepository<DownloadInvite, String> {
    Optional<DownloadInvite> findByCode(String code);
    boolean existsByCode(String code);
}
