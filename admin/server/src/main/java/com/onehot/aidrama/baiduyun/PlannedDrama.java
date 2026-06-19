package com.onehot.aidrama.baiduyun;

import java.util.List;

public record PlannedDrama(
        String title,
        String summary,
        String summaryPath,
        String sourcePath,
        String coverPath,
        int episodeCount,
        List<PlannedEpisode> episodes
) {
}
