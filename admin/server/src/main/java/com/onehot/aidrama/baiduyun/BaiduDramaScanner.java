package com.onehot.aidrama.baiduyun;

import com.onehot.aidrama.categories.DramaCategoryClassifier;
import com.onehot.aidrama.configs.SystemConfigService;
import com.onehot.aidrama.dramas.Drama;
import com.onehot.aidrama.dramas.DramaDurationEstimator;
import com.onehot.aidrama.dramas.DramaEpisode;
import com.onehot.aidrama.dramas.DramaRepository;
import com.onehot.aidrama.dramas.DramaStatus;
import com.onehot.aidrama.system.SystemTaskService;
import com.onehot.aidrama.system.SystemTaskType;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;

@Service
public class BaiduDramaScanner {
    private static final Logger LOGGER = LoggerFactory.getLogger(BaiduDramaScanner.class);

    private final BaiduPanClient baiduPanClient;
    private final DramaRepository dramaRepository;
    private final SystemConfigService configService;
    private final BaiduAssetStorage assetStorage;
    private final SystemTaskService systemTaskService;
    private final AtomicBoolean scheduledScanRunning = new AtomicBoolean(false);
    private final BaiduDramaImportPlanner importPlanner = new BaiduDramaImportPlanner();
    private final DramaCategoryClassifier classifier = new DramaCategoryClassifier();

    @Autowired
    public BaiduDramaScanner(
            BaiduPanClient baiduPanClient,
            DramaRepository dramaRepository,
            SystemConfigService configService,
            BaiduAssetStorage assetStorage
    ) {
        this(baiduPanClient, dramaRepository, configService, assetStorage, null);
    }

    public BaiduDramaScanner(
            BaiduPanClient baiduPanClient,
            DramaRepository dramaRepository,
            SystemConfigService configService,
            BaiduAssetStorage assetStorage,
            SystemTaskService systemTaskService
    ) {
        this.baiduPanClient = baiduPanClient;
        this.dramaRepository = dramaRepository;
        this.configService = configService;
        this.assetStorage = assetStorage;
        this.systemTaskService = systemTaskService;
    }

    @Scheduled(
            fixedDelayString = "${aidrama.baidu.scan-fixed-delay-ms:600000}",
            initialDelayString = "${aidrama.baidu.scan-initial-delay-ms:60000}"
    )
    public void scheduledScan() {
        if (!scheduledScanRunning.compareAndSet(false, true)) {
            LOGGER.warn("Skip Baidu scheduled scan because previous scan is still running");
            return;
        }
        try {
            runScheduledScan();
        } finally {
            scheduledScanRunning.set(false);
        }
    }

    private void runScheduledScan() {
        boolean enabled = configService.get("baidu.scanEnabled").map(Boolean::parseBoolean).orElse(true);
        if (enabled) {
            if (systemTaskService == null) {
                scanLatestConfiguredRoot();
                return;
            }
            String remoteRoot = configService.get("baidu.scanRoot").orElse("/drama/真人剧/2026");
            systemTaskService.run(
                    SystemTaskType.BAIDU_PAN_SCAN,
                    "定时扫描百度网盘",
                    "scheduled",
                    mapOf("remoteRoot", remoteRoot),
                    this::scanLatestConfiguredRoot,
                    dramas -> new SystemTaskService.TaskResult(
                            "导入 %d 部短剧".formatted(dramas.size()),
                            mapOf(
                                    "importedCount", dramas.size(),
                                    "dramas", dramas.stream().map(this::dramaSummary).toList()
                            )
                    )
            );
        }
    }

    public List<Drama> scanLatestConfiguredRoot() {
        return scanLatestDate(configService.get("baidu.scanRoot").orElse("/drama/真人剧/2026"));
    }

    public List<Drama> scanLatestDate(String yearRoot) {
        BaiduPanEntry latestDate = importPlanner.pickLatestDateDirectory(baiduPanClient.listDirectory(yearRoot))
                .orElseThrow(() -> new BaiduPanException("No date directory found under " + yearRoot));
        List<Drama> dramas = scanDateDirectory(latestDate.path());
        configService.put("baidu.lastScanAt", Instant.now().toString(), false);
        return dramas;
    }

    public Optional<String> lastScanAt() {
        return configService.get("baidu.lastScanAt");
    }

    public List<Drama> scanDateDirectory(String dateDirectory) {
        return baiduPanClient.listDirectory(dateDirectory).stream()
                .filter(BaiduPanEntry::directory)
                .map(this::importDramaSafely)
                .flatMap(Optional::stream)
                .toList();
    }

    public List<Drama> repairImportedAssets() {
        return dramaRepository.findAll().stream()
                .filter(this::needsAssetRepair)
                .map(this::repairImportedDramaSafely)
                .flatMap(Optional::stream)
                .toList();
    }

    public SyncResult syncImportedAssets(List<String> ids) {
        List<String> requestedIds = ids == null ? List.of() : ids.stream()
                .filter(id -> id != null && !id.isBlank())
                .distinct()
                .toList();
        List<Drama> synced = new ArrayList<>();
        Set<String> foundIds = new HashSet<>();
        for (Drama drama : dramaRepository.findAllById(requestedIds)) {
            foundIds.add(drama.getId());
            try {
                synced.add(syncImportedDrama(drama));
            } catch (BaiduPanException | IllegalArgumentException exception) {
                LOGGER.warn("Skip Baidu asset sync for {}: {}", drama.getSourcePath(), rootCauseMessage(exception));
            }
        }
        int failed = requestedIds.size() - synced.size();
        return new SyncResult(requestedIds.size(), synced.size(), failed, synced);
    }

    public List<ClientAssetSyncPlan> clientAssetSyncPlans(List<String> ids) {
        List<String> requestedIds = ids == null ? List.of() : ids.stream()
                .filter(id -> id != null && !id.isBlank())
                .distinct()
                .toList();
        List<ClientAssetSyncPlan> plans = new ArrayList<>();
        for (Drama drama : dramaRepository.findAllById(requestedIds)) {
            try {
                plans.add(clientAssetSyncPlan(drama));
            } catch (BaiduPanException | IllegalArgumentException exception) {
                plans.add(new ClientAssetSyncPlan(
                        drama.getId(),
                        drama.getTitle(),
                        drama.getSourcePath(),
                        null,
                        null,
                        null,
                        null,
                        rootCauseMessage(exception)
                ));
            }
        }
        return plans;
    }

    public Drama applyClientAssetSync(String id, String summary, String coverPath, byte[] coverBytes) {
        Drama drama = dramaRepository.findById(id)
                .orElseThrow(() -> new BaiduPanException("Drama not found: " + id));
        if (summary != null && !summary.isBlank() && !looksLikeBaiduError(summary)) {
            drama.setSummary(summary.trim());
        }
        if (coverBytes != null && coverBytes.length > 0) {
            if (coverPath == null || coverPath.isBlank()) {
                throw new BaiduPanException("Cover path is required");
            }
            drama.setCoverUrl(assetStorage.storeCoverBytes(coverPath, coverBytes));
        }
        return dramaRepository.save(drama);
    }

    private ClientAssetSyncPlan clientAssetSyncPlan(Drama drama) {
        if (!hasSourcePath(drama)) {
            throw new IllegalArgumentException("Drama has no source path");
        }
        PlannedDrama planned = importPlanner.planDrama(
                new BaiduPanEntry(drama.getSourcePath(), fileName(drama.getSourcePath()), true, null, 0),
                baiduPanClient.listDirectory(drama.getSourcePath())
        );
        String summaryDownloadUrl = isBlank(planned.summaryPath())
                ? null
                : baiduPanClient.createDownloadUrl(planned.summaryPath());
        String coverDownloadUrl = isBlank(planned.coverPath())
                ? null
                : baiduPanClient.createDownloadUrl(planned.coverPath());
        return new ClientAssetSyncPlan(
                drama.getId(),
                drama.getTitle(),
                drama.getSourcePath(),
                planned.summaryPath(),
                summaryDownloadUrl,
                planned.coverPath(),
                coverDownloadUrl,
                null
        );
    }

    private Drama syncImportedDrama(Drama drama) {
        if (!hasSourcePath(drama)) {
            throw new IllegalArgumentException("Drama has no source path");
        }
        PlannedDrama planned = importPlanner.planDrama(
                new BaiduPanEntry(drama.getSourcePath(), fileName(drama.getSourcePath()), true, null, 0),
                baiduPanClient.listDirectory(drama.getSourcePath())
        );
        drama.setSummary(resolveSummary(planned));
        if (!isBlank(planned.coverPath())) {
            drama.setCoverUrl(resolveRequiredCoverUrl(planned));
        }
        return dramaRepository.save(drama);
    }

    private Optional<Drama> repairImportedDramaSafely(Drama drama) {
        try {
            return Optional.of(repairImportedDrama(drama));
        } catch (BaiduPanException exception) {
            LOGGER.warn("Skip Baidu asset repair for {}: {}", drama.getSourcePath(), exception.getMessage());
            return Optional.empty();
        }
    }

    private boolean needsAssetRepair(Drama drama) {
        return hasSourcePath(drama)
                && (looksLikeBaiduError(drama.getSummary()) || isRemoteBaiduCover(drama.getCoverUrl()) || drama.getCoverUrl() == null);
    }

    private Drama repairImportedDrama(Drama drama) {
        PlannedDrama planned = importPlanner.planDrama(
                new BaiduPanEntry(drama.getSourcePath(), fileName(drama.getSourcePath()), true, null, 0),
                baiduPanClient.listDirectory(drama.getSourcePath())
        );
        if (looksLikeBaiduError(drama.getSummary()) || drama.getSummary() == null || drama.getSummary().isBlank()) {
            drama.setSummary(resolveSummary(planned));
        }
        if (isRemoteBaiduCover(drama.getCoverUrl()) || drama.getCoverUrl() == null || drama.getCoverUrl().isBlank()) {
            drama.setCoverUrl(resolveCoverUrl(planned));
        }
        return dramaRepository.save(drama);
    }

    private Optional<Drama> importDramaSafely(BaiduPanEntry dramaDir) {
        try {
            return Optional.of(importDrama(dramaDir));
        } catch (DuplicateDramaException exception) {
            LOGGER.info("Skip duplicate Baidu drama import for {}: {}", dramaDir.path(), exception.getMessage());
            return Optional.empty();
        } catch (BaiduPanException | IllegalArgumentException exception) {
            LOGGER.warn("Skip Baidu drama import for {}: {}", dramaDir.path(), rootCauseMessage(exception));
            return Optional.empty();
        }
    }

    private Drama importDrama(BaiduPanEntry dramaDir) {
        PlannedDrama planned = importPlanner.planDrama(dramaDir, baiduPanClient.listDirectory(dramaDir.path()));
        List<Drama> matches = dramaRepository.findAllBySourcePath(planned.sourcePath());
        Optional<Drama> existing = matches.stream().findFirst();
        if (matches.size() > 1) {
            LOGGER.warn(
                    "Duplicate drama sourcePath found, using first record: sourcePath={}, ids={}",
                    planned.sourcePath(),
                    matches.stream().map(Drama::getId).toList()
            );
        }
        boolean newDrama = existing.isEmpty();
        if (newDrama) {
            skipIfOriginalTitleAndEpisodeCountAlreadyExist(planned);
        }
        Drama drama = existing.orElseGet(Drama::new);
        if (existing.isPresent()) {
            mergeScannedMetadata(drama, planned);
        } else {
            drama.setTitle(planned.title());
            if (scanDownloadAssetsEnabled()) {
                drama.setSummary(resolveSummary(planned));
                drama.setCoverUrl(resolveCoverUrl(planned));
            } else {
                drama.setSummary(planned.summary());
            }
        }
        drama.setSource("BAIDU_PAN");
        drama.setSourcePath(planned.sourcePath());
        if (newDrama && drama.getStatus() != DramaStatus.DISABLED) {
            drama.setStatus(DramaStatus.DRAFT);
        }
        Set<String> categoryCodes = classifier.classifyCodes(planned.title(), planned.summary());
        drama.setCategoryIds(List.copyOf(categoryCodes));
        drama.setEpisodes(planned.episodes().stream().map(this::episodeFrom).toList());
        ensureTotalMinutes(drama);
        return dramaRepository.save(drama);
    }

    private void skipIfOriginalTitleAndEpisodeCountAlreadyExist(PlannedDrama planned) {
        dramaRepository.findAllByTitle(planned.title()).stream()
                .filter(drama -> episodeCount(drama) == planned.episodeCount())
                .findFirst()
                .ifPresent(existing -> {
                    throw new DuplicateDramaException(
                            "originalTitle=%s, episodeCount=%d, existingId=%s, existingSourcePath=%s"
                                    .formatted(planned.title(), planned.episodeCount(), existing.getId(), existing.getSourcePath())
                    );
                });
    }

    private int episodeCount(Drama drama) {
        return drama.getEpisodes() == null ? 0 : drama.getEpisodes().size();
    }

    private void ensureTotalMinutes(Drama drama) {
        if (DramaDurationEstimator.needsTotalMinutes(drama)) {
            drama.setTotalMinutes(DramaDurationEstimator.estimateTotalMinutes(drama));
        }
    }

    private void mergeScannedMetadata(Drama drama, PlannedDrama planned) {
        if (isBlank(drama.getTitle())) {
            drama.setTitle(planned.title());
        }
        if (!scanDownloadAssetsEnabled()) {
            if (isBlank(drama.getSummary())) {
                drama.setSummary(planned.summary());
            }
            return;
        }
        if (isBlank(drama.getSummary())) {
            drama.setSummary(resolveSummary(planned));
        } else if (!isBlank(planned.summaryPath())) {
            drama.setSummary(resolveSummary(planned));
        }
        if (isBlank(drama.getCoverUrl()) || isRemoteBaiduCover(drama.getCoverUrl())) {
            drama.setCoverUrl(resolveCoverUrl(planned));
        } else if (!isBlank(planned.coverPath())) {
            String coverUrl = resolveCoverUrl(planned);
            if (!isBlank(coverUrl)) {
                drama.setCoverUrl(coverUrl);
            }
        }
    }

    private boolean scanDownloadAssetsEnabled() {
        return configService.get("baidu.scanDownloadAssets")
                .map(Boolean::parseBoolean)
                .orElse(true);
    }

    private String resolveSummary(PlannedDrama planned) {
        if (planned.summaryPath() == null || planned.summaryPath().isBlank()) {
            return planned.summary();
        }
        String summary;
        try {
            summary = baiduPanClient.readTextFile(planned.summaryPath());
        } catch (BaiduPanException exception) {
            return planned.summary();
        }
        if (summary == null || summary.isBlank()) {
            return planned.summary();
        }
        if (looksLikeBaiduError(summary)) {
            return planned.summary();
        }
        return summary.trim();
    }

    private String resolveCoverUrl(PlannedDrama planned) {
        if (planned.coverPath() == null || planned.coverPath().isBlank()) {
            return null;
        }
        try {
            return assetStorage.storeCover(planned.coverPath(), baiduPanClient);
        } catch (BaiduPanException exception) {
            LOGGER.warn("Baidu cover download failed: coverPath={}, reason={}", planned.coverPath(), rootCauseMessage(exception));
            return null;
        }
    }

    private String resolveRequiredCoverUrl(PlannedDrama planned) {
        try {
            return assetStorage.storeCover(planned.coverPath(), baiduPanClient);
        } catch (BaiduPanException exception) {
            throw new BaiduPanException("Baidu cover download failed for " + planned.coverPath() + ": " + exception.getMessage(), exception);
        }
    }

    private boolean looksLikeBaiduError(String value) {
        if (value == null) {
            return false;
        }
        String trimmed = value.trim();
        return trimmed.startsWith("{")
                && (trimmed.contains("\"error_code\"") || trimmed.contains("\"errno\""))
                && trimmed.contains("\"request_id\"");
    }

    private boolean isRemoteBaiduCover(String value) {
        return value != null && (value.contains("pan.baidu.com") || value.contains("baidu.com"));
    }

    private String rootCauseMessage(Throwable throwable) {
        Throwable cursor = throwable;
        while (cursor.getCause() != null) {
            cursor = cursor.getCause();
        }
        String message = cursor.getMessage();
        return cursor == throwable
                ? String.valueOf(message)
                : throwable.getMessage() + " (" + cursor.getClass().getSimpleName() + ": " + message + ")";
    }

    private boolean hasSourcePath(Drama drama) {
        return drama.getSourcePath() != null && !drama.getSourcePath().isBlank();
    }

    private boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private String fileName(String path) {
        int slash = path.lastIndexOf('/');
        return slash < 0 ? path : path.substring(slash + 1);
    }

    private DramaEpisode episodeFrom(PlannedEpisode planned) {
        DramaEpisode episode = new DramaEpisode();
        episode.setEpisodeNo(planned.episodeNo());
        episode.setTitle(planned.title());
        episode.setSourcePath(planned.path());
        episode.setFsId(planned.fsId());
        episode.setSize(planned.size());
        return episode;
    }

    private Map<String, Object> dramaSummary(Drama drama) {
        return mapOf(
                "id", drama.getId(),
                "title", drama.getTitle(),
                "sourcePath", drama.getSourcePath(),
                "episodeCount", drama.getEpisodes() == null ? 0 : drama.getEpisodes().size(),
                "status", drama.getStatus()
        );
    }

    private Map<String, Object> mapOf(Object... pairs) {
        Map<String, Object> values = new LinkedHashMap<>();
        for (int index = 0; index < pairs.length; index += 2) {
            values.put(String.valueOf(pairs[index]), pairs[index + 1]);
        }
        return values;
    }

    public record SyncResult(int requested, int succeeded, int failed, List<Drama> dramas) {
    }

    public record ClientAssetSyncPlan(
            String dramaId,
            String title,
            String sourcePath,
            String summaryPath,
            String summaryDownloadUrl,
            String coverPath,
            String coverDownloadUrl,
            String errorMessage
    ) {
    }

    private static class DuplicateDramaException extends RuntimeException {
        DuplicateDramaException(String message) {
            super(message);
        }
    }
}
