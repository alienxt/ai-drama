package com.onehot.aidrama.baiduyun;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class BaiduDramaImportPlannerTest {
    @Test
    void picksLatestChineseMonthDayDirectory() {
        BaiduDramaImportPlanner planner = new BaiduDramaImportPlanner();

        BaiduPanEntry latest = planner.pickLatestDateDirectory(List.of(
                new BaiduPanEntry("/root/6月2日", "6月2日", true, 1L, 0),
                new BaiduPanEntry("/root/6月13日", "6月13日", true, 2L, 0),
                new BaiduPanEntry("/root/readme.txt", "readme.txt", false, 3L, 1)
        )).orElseThrow();

        assertThat(latest.path()).isEqualTo("/root/6月13日");
    }

    @Test
    void parsesDramaDirectoryNameAndEpisodes() {
        BaiduDramaImportPlanner planner = new BaiduDramaImportPlanner();

        PlannedDrama drama = planner.planDrama(
                new BaiduPanEntry("/root/1.神医归来，开局抢婚校花老婆（80集）吴明宇＆赵慧", "1.神医归来，开局抢婚校花老婆（80集）吴明宇＆赵慧", true, 1L, 0),
                List.of(
                        new BaiduPanEntry("/root/0.jpg", "0.jpg", false, 10L, 100),
                        new BaiduPanEntry("/root/02.mp4", "02.mp4", false, 12L, 200),
                        new BaiduPanEntry("/root/01.mp4", "01.mp4", false, 11L, 100)
                )
        );

        assertThat(drama.title()).isEqualTo("神医归来，开局抢婚校花老婆");
        assertThat(drama.summary()).contains("吴明宇").contains("80集");
        assertThat(drama.coverPath()).isEqualTo("/root/0.jpg");
        assertThat(drama.episodeCount()).isEqualTo(80);
        assertThat(drama.episodes()).extracting(PlannedEpisode::episodeNo).containsExactly(1, 2);
    }

    @Test
    void readsSummaryFromTextFileWhenPresent() {
        BaiduDramaImportPlanner planner = new BaiduDramaImportPlanner();

        PlannedDrama drama = planner.planDrama(
                new BaiduPanEntry("/root/2.天降萌宝（60集）", "2.天降萌宝（60集）", true, 1L, 0),
                List.of(
                        new BaiduPanEntry("/root/cover.png", "cover.png", false, 10L, 100),
                        new BaiduPanEntry("/root/简介.txt", "简介.txt", false, 11L, 200),
                        new BaiduPanEntry("/root/01.mp4", "01.mp4", false, 12L, 100)
                )
        );

        assertThat(drama.summaryPath()).isEqualTo("/root/简介.txt");
    }

    @Test
    void prefersZeroNamedImageAsCoverBeforeOtherImages() {
        BaiduDramaImportPlanner planner = new BaiduDramaImportPlanner();

        PlannedDrama drama = planner.planDrama(
                new BaiduPanEntry("/root/3.替嫁成婚（36集）", "3.替嫁成婚（36集）", true, 1L, 0),
                List.of(
                        new BaiduPanEntry("/root/1.jpg", "1.jpg", false, 10L, 100),
                        new BaiduPanEntry("/root/0.png", "0.png", false, 11L, 100),
                        new BaiduPanEntry("/root/01.mp4", "01.mp4", false, 12L, 100)
                )
        );

        assertThat(drama.coverPath()).isEqualTo("/root/0.png");
    }
}
