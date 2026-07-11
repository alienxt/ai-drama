package com.onehot.aidrama.dramas;

import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.domain.Sort;

import java.time.Instant;
import java.util.List;

public interface DramaRepository extends MongoRepository<Drama, String> {
    List<Drama> findByStatus(DramaStatus status);
    List<Drama> findByStatusAndCreatedAtGreaterThanEqual(DramaStatus status, Instant createdAt, Sort sort);
    List<Drama> findAllBySourcePath(String sourcePath);
    List<Drama> findAllByTitle(String title);
}
