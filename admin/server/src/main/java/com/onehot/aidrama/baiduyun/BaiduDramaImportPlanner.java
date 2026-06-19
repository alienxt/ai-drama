package com.onehot.aidrama.baiduyun;

import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class BaiduDramaImportPlanner {
    private static final Pattern DATE_DIR = Pattern.compile("^(\\d{1,2})月(\\d{1,2})日$");
    private static final Pattern LEADING_INDEX = Pattern.compile("^\\d+[.．、\\s]*");
    private static final Pattern EPISODE_COUNT = Pattern.compile("[（(](\\d+)集[）)]");
    private static final Pattern EPISODE_FILE = Pattern.compile("^(\\d+).*\\.(mp4|mov|m4v)$", Pattern.CASE_INSENSITIVE);

    public Optional<BaiduPanEntry> pickLatestDateDirectory(List<BaiduPanEntry> entries) {
        return entries.stream()
                .filter(BaiduPanEntry::directory)
                .filter(entry -> DATE_DIR.matcher(entry.name()).matches())
                .max(Comparator.comparingInt(entry -> monthDayScore(entry.name())));
    }

    public PlannedDrama planDrama(BaiduPanEntry dramaDir, List<BaiduPanEntry> children) {
        String rawName = LEADING_INDEX.matcher(dramaDir.name()).replaceFirst("").trim();
        int episodeCount = extractEpisodeCount(rawName);
        String title = titleBeforeEpisodeCount(rawName);
        String summary = rawName.equals(title) ? title : rawName;
        String coverPath = children.stream()
                .filter(entry -> !entry.directory())
                .filter(entry -> isImage(entry.name()))
                .sorted(Comparator.comparingInt(entry -> coverPriority(entry.name())))
                .map(BaiduPanEntry::path)
                .findFirst()
                .orElse(null);
        String summaryPath = children.stream()
                .filter(entry -> !entry.directory())
                .filter(entry -> isSummaryText(entry.name()))
                .map(BaiduPanEntry::path)
                .findFirst()
                .orElse(null);
        List<PlannedEpisode> episodes = children.stream()
                .filter(entry -> !entry.directory())
                .map(this::toEpisode)
                .flatMap(Optional::stream)
                .sorted(Comparator.comparingInt(PlannedEpisode::episodeNo))
                .toList();
        int resolvedEpisodeCount = episodeCount > 0 ? episodeCount : episodes.size();
        return new PlannedDrama(title, summary, summaryPath, dramaDir.path(), coverPath, resolvedEpisodeCount, episodes);
    }

    private Optional<PlannedEpisode> toEpisode(BaiduPanEntry entry) {
        Matcher matcher = EPISODE_FILE.matcher(entry.name());
        if (!matcher.matches()) {
            return Optional.empty();
        }
        int episodeNo = Integer.parseInt(matcher.group(1));
        return Optional.of(new PlannedEpisode(episodeNo, entry.name(), entry.path(), entry.fsId(), entry.size()));
    }

    private boolean isImage(String name) {
        String lower = name.toLowerCase();
        return lower.endsWith(".jpg") || lower.endsWith(".jpeg") || lower.endsWith(".png") || lower.endsWith(".webp");
    }

    private int coverPriority(String name) {
        String stem = fileStem(name.toLowerCase());
        if (stem.equals("cover") || stem.equals("封面")) {
            return 0;
        }
        if (stem.equals("0")) {
            return 1;
        }
        return 2;
    }

    private String fileStem(String name) {
        int dot = name.lastIndexOf('.');
        return dot < 0 ? name : name.substring(0, dot);
    }

    private boolean isSummaryText(String name) {
        String lower = name.toLowerCase();
        return lower.equals("简介.txt") || lower.equals("summary.txt") || lower.equals("intro.txt")
                || lower.equals("简介.md") || lower.equals("summary.md") || lower.equals("intro.md");
    }

    private int extractEpisodeCount(String rawName) {
        Matcher matcher = EPISODE_COUNT.matcher(rawName);
        if (!matcher.find()) {
            return 0;
        }
        return Integer.parseInt(matcher.group(1));
    }

    private String titleBeforeEpisodeCount(String rawName) {
        Matcher matcher = EPISODE_COUNT.matcher(rawName);
        if (!matcher.find()) {
            return rawName;
        }
        return rawName.substring(0, matcher.start()).trim();
    }

    private int monthDayScore(String name) {
        Matcher matcher = DATE_DIR.matcher(name);
        if (!matcher.matches()) {
            return 0;
        }
        return Integer.parseInt(matcher.group(1)) * 100 + Integer.parseInt(matcher.group(2));
    }
}
