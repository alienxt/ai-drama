package com.onehot.aidrama.media;

import org.springframework.data.mongodb.repository.MongoRepository;

import java.util.List;

public interface MediaAccountRepository extends MongoRepository<MediaAccount, String> {
    List<MediaAccount> findByOwnerAccountId(String ownerAccountId);
}

