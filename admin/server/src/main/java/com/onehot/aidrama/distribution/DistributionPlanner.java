package com.onehot.aidrama.distribution;

import com.onehot.aidrama.dramas.Drama;
import com.onehot.aidrama.dramas.DramaSources;
import com.onehot.aidrama.dramas.DramaStatus;
import com.onehot.aidrama.media.MediaAccount;
import com.onehot.aidrama.media.MediaAccountStatus;

import java.util.HashSet;
import java.util.List;

public class DistributionPlanner {
    public boolean canDistribute(MediaAccount mediaAccount, Drama drama) {
        if (mediaAccount.getStatus() != MediaAccountStatus.ACTIVE) {
            return false;
        }
        if (mediaAccount.getDistributionPolicy() == null || !mediaAccount.getDistributionPolicy().isEnabled()) {
            return false;
        }
        if (!canEnterTaskQueue(drama) || drama.getEpisodes() == null || drama.getEpisodes().isEmpty()) {
            return false;
        }
        var wanted = new HashSet<>(mediaAccount.getDistributionPolicy().getCategoryIds() == null
                ? List.<String>of()
                : mediaAccount.getDistributionPolicy().getCategoryIds());
        return wanted.isEmpty() || drama.getCategoryIds().stream().anyMatch(wanted::contains);
    }

    private boolean canEnterTaskQueue(Drama drama) {
        if (drama == null) {
            return false;
        }
        if (drama.getStatus() == DramaStatus.READY) {
            return true;
        }
        return drama.getStatus() == DramaStatus.DRAFT
                && DramaSources.BAIDU_PAN.equals(DramaSources.normalize(drama.getSource()))
                && hasText(drama.getSourcePath());
    }

    private boolean hasText(String value) {
        return value != null && !value.isBlank();
    }
}
