package com.onehot.aidrama.dramas;

import org.springframework.data.mongodb.repository.MongoRepository;

import java.util.List;

public interface DramaRepository extends MongoRepository<Drama, String> {
    List<Drama> findByStatus(DramaStatus status);
    List<Drama> findAllBySourcePath(String sourcePath);
}
