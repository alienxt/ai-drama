package com.onehot.aidrama.dramas;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class DramaDurationEstimatorTest {
    @Test
    void estimatesStableRoundedTotalBetweenOneAndTwoMinutesPerEpisode() {
        int total = DramaDurationEstimator.estimateTotalMinutes(80, "/root/短剧/神医归来（80集）");

        assertThat(total).isBetween(80, 160);
        assertThat(total % 10).isZero();
        assertThat(DramaDurationEstimator.estimateTotalMinutes(80, "/root/短剧/神医归来（80集）"))
                .isEqualTo(total);
    }

    @Test
    void zeroEpisodeDramaHasZeroMinutes() {
        assertThat(DramaDurationEstimator.estimateTotalMinutes(0, "empty")).isZero();
    }

    @Test
    void nonRoundedExistingValueNeedsBackfill() {
        Drama drama = new Drama();
        drama.setTotalMinutes(121);

        assertThat(DramaDurationEstimator.needsTotalMinutes(drama)).isTrue();
    }

    @Test
    void roundedExistingValueDoesNotNeedBackfill() {
        Drama drama = new Drama();
        drama.setTotalMinutes(120);

        assertThat(DramaDurationEstimator.needsTotalMinutes(drama)).isFalse();
    }

    @Test
    void estimatesCostByTotalMinutesWithinOneToFiveWan() {
        assertThat(DramaDurationEstimator.estimateCostAmountWan(1)).isEqualTo(1);
        assertThat(DramaDurationEstimator.estimateCostAmountWan(30)).isEqualTo(1);
        assertThat(DramaDurationEstimator.estimateCostAmountWan(31)).isEqualTo(2);
        assertThat(DramaDurationEstimator.estimateCostAmountWan(100)).isEqualTo(4);
        assertThat(DramaDurationEstimator.estimateCostAmountWan(180)).isEqualTo(5);
    }

    @Test
    void estimatesCostFromDramaTotalMinutes() {
        Drama drama = new Drama();
        drama.setTotalMinutes(60);

        assertThat(DramaDurationEstimator.estimateCostAmountWan(drama)).isEqualTo(2);
    }

    @Test
    void costNeedsBackfillWhenStoredValueDoesNotMatchMinutesRule() {
        Drama drama = new Drama();
        drama.setTotalMinutes(100);
        drama.setCostAmountWan(2);

        assertThat(DramaDurationEstimator.needsCostAmountWan(drama)).isTrue();
    }

    @Test
    void costDoesNotNeedBackfillWhenStoredValueMatchesMinutesRule() {
        Drama drama = new Drama();
        drama.setTotalMinutes(100);
        drama.setCostAmountWan(4);

        assertThat(DramaDurationEstimator.needsCostAmountWan(drama)).isFalse();
    }
}
