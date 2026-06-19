package com.onehot.aidrama.distribution;

import com.onehot.aidrama.dramas.Drama;
import com.onehot.aidrama.dramas.DramaEpisode;
import com.onehot.aidrama.dramas.DramaStatus;
import com.onehot.aidrama.media.DistributionPolicy;
import com.onehot.aidrama.media.MediaAccount;
import com.onehot.aidrama.media.MediaAccountStatus;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class DistributionPlannerTest {
    @Test
    void createsTaskWhenMediaPolicyMatchesDramaCategory() {
        DistributionPlanner planner = new DistributionPlanner();
        Drama drama = new Drama();
        drama.setId("drama-1");
        drama.setStatus(DramaStatus.READY);
        drama.setCategoryIds(List.of("romance"));
        drama.setEpisodes(List.of(new DramaEpisode()));

        MediaAccount media = new MediaAccount();
        media.setId("media-1");
        media.setStatus(MediaAccountStatus.ACTIVE);
        DistributionPolicy policy = new DistributionPolicy();
        policy.setCategoryIds(List.of("romance", "urban"));
        policy.setEnabled(true);
        media.setDistributionPolicy(policy);

        assertThat(planner.canDistribute(media, drama)).isTrue();
    }

    @Test
    void pausedMediaAccountCannotDistribute() {
        DistributionPlanner planner = new DistributionPlanner();
        Drama drama = new Drama();
        drama.setId("drama-1");
        drama.setStatus(DramaStatus.READY);
        drama.setCategoryIds(List.of("romance"));
        drama.setEpisodes(List.of(new DramaEpisode()));

        MediaAccount media = new MediaAccount();
        media.setId("media-1");
        media.setStatus(MediaAccountStatus.PAUSED);
        DistributionPolicy policy = new DistributionPolicy();
        policy.setCategoryIds(List.of("romance"));
        policy.setEnabled(true);
        media.setDistributionPolicy(policy);

        assertThat(planner.canDistribute(media, drama)).isFalse();
    }
}
