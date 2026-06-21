package com.onehot.aidrama.dramas;

import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.domain.Sort;

import java.time.Instant;
import java.util.List;

public interface DramaRepository extends MongoRepository<Drama, String> {
    List<Drama> findByStatus(DramaStatus status);
    List<Drama> findByStatusAndUpdatedAtGreaterThanEqual(DramaStatus status, Instant updatedAt, Sort sort);
    List<Drama> findAllBySourcePath(String sourcePath);
    List<Drama> findAllByTitle(String title);
}
