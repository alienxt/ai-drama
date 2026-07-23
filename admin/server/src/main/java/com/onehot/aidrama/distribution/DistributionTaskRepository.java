package com.onehot.aidrama.distribution;

import org.springframework.data.mongodb.repository.MongoRepository;

import com.onehot.aidrama.media.MediaPlatform;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

public interface DistributionTaskRepository extends MongoRepository<DistributionTask, String> {
    Optional<DistributionTask> findFirstByStatusOrderByCreatedAtAsc(DistributionTaskStatus status);
    Optional<DistributionTask> findFirstByStatusAndMediaAccountIdInOrderByCreatedAtAsc(
            DistributionTaskStatus status,
            List<String> mediaAccountIds
    );
    Optional<DistributionTask> findFirstByStatusAndMediaAccountIdInOrderByPriorityDescCreatedAtAsc(
            DistributionTaskStatus status,
            List<String> mediaAccountIds
    );
    List<DistributionTask> findByStatusAndMediaAccountIdIn(
            DistributionTaskStatus status,
            List<String> mediaAccountIds
    );
    Optional<DistributionTask> findFirstByDramaIdAndStatusAndMediaAccountIdInOrderByCreatedAtAsc(
            String dramaId,
            DistributionTaskStatus status,
            List<String> mediaAccountIds
    );
    List<DistributionTask> findByStatusAndPriorityGreaterThanAndMediaAccountIdIn(
            DistributionTaskStatus status,
            int priority,
            List<String> mediaAccountIds
    );
    List<DistributionTask> findByDramaId(String dramaId);
    boolean existsByDramaIdAndPlatform(String dramaId, MediaPlatform platform);
    boolean existsByMediaAccountIdAndDramaId(String mediaAccountId, String dramaId);
    boolean existsByMediaAccountIdAndDramaIdAndStatusNotIn(
            String mediaAccountId,
            String dramaId,
            List<DistributionTaskStatus> statuses
    );
    Optional<DistributionTask> findFirstByMediaAccountIdAndDramaIdAndStatusOrderByCreatedAtDesc(
            String mediaAccountId,
            String dramaId,
            DistributionTaskStatus status
    );
    long countByMediaAccountIdInAndUpdatedAtGreaterThanEqualAndStatus(
            List<String> mediaAccountIds,
            Instant updatedAt,
            DistributionTaskStatus status
    );
    long countByMediaAccountIdInAndClaimedAtGreaterThanEqual(
            List<String> mediaAccountIds,
            Instant claimedAt
    );
    long countByMediaAccountIdInAndClaimedAtIsNullAndUpdatedAtGreaterThanEqualAndStatusIn(
            List<String> mediaAccountIds,
            Instant updatedAt,
            List<DistributionTaskStatus> statuses
    );
    default boolean existsActiveByDramaId(String dramaId) {
        return existsByDramaIdAndStatusNotIn(dramaId, List.of(DistributionTaskStatus.FAILED, DistributionTaskStatus.CANCELLED));
    }

    boolean existsByDramaIdAndStatusNotIn(String dramaId, List<DistributionTaskStatus> statuses);
}
