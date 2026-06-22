package com.onehot.aidrama.dramas;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class DramaDurationEstimatorTest {
    @Test
    void estimatesStableIntegerTotalBetweenOneAndTwoMinutesPerEpisode() {
        int total = DramaDurationEstimator.estimateTotalMinutes(80, "/root/短剧/神医归来（80集）");

        assertThat(total).isBetween(80, 160);
        assertThat(DramaDurationEstimator.estimateTotalMinutes(80, "/root/短剧/神医归来（80集）"))
                .isEqualTo(total);
    }

    @Test
    void zeroEpisodeDramaHasZeroMinutes() {
        assertThat(DramaDurationEstimator.estimateTotalMinutes(0, "empty")).isZero();
    }
}
