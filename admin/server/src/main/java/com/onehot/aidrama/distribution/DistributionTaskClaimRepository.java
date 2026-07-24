package com.onehot.aidrama.distribution;

import org.springframework.data.mongodb.repository.MongoRepository;

import java.time.Instant;
import java.util.List;

public interface DistributionTaskClaimRepository extends MongoRepository<DistributionTaskClaim, String> {
    long countByMediaAccountIdInAndClaimedAtGreaterThanEqual(
            List<String> mediaAccountIds,
            Instant claimedAt
    );

    long countByMediaAccountIdAndClaimedAtGreaterThanEqual(
            String mediaAccountId,
            Instant claimedAt
    );
}
