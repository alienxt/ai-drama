package com.onehot.aidrama.baiduyun;

import com.onehot.aidrama.dramas.Drama;
import com.onehot.aidrama.dramas.DramaAiService;
import com.onehot.aidrama.dramas.DramaRepository;
import com.onehot.aidrama.dramas.DramaStatus;
import com.onehot.aidrama.configs.SystemConfigService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.Instant;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicBoolean;

@Service
public class BaiduDramaPreparationService {
    private static final Logger LOGGER = LoggerFactory.getLogger(BaiduDramaPreparationService.class);

    private final DramaRepository repository;
    private final DramaAiService aiService;
    private final SystemConfigService configService;
    private final AtomicBoolean preparing = new AtomicBoolean(false);

    public BaiduDramaPreparationService(DramaRepository repository, DramaAiService aiService, SystemConfigService configService) {
        this.repository = repository;
        this.aiService = aiService;
        this.configService = configService;
    }

    @Scheduled(
            fixedDelayString = "${aidrama.baidu.prepare-fixed-delay-ms:10000}",
            initialDelayString = "${aidrama.baidu.prepare-initial-delay-ms:10000}"
    )
    public void scheduledPrepareNextPendingDrama() {
        if (prepareOnDemandOnly()) {
            return;
        }
        if (!preparing.compareAndSet(false, true)) {
            return;
        }
        try {
            prepareNextPendingDrama();
        } finally {
            preparing.set(false);
        }
    }

    public Optional<Drama> prepareNextPendingDrama() {
        return repository.findAll().stream()
                .filter(this::needsPreparation)
                .findFirst()
                .map(this::prepareForDistribution);
    }

    public Drama prepareForDistribution(Drama drama) {
        return prepareForDistribution(drama, false);
    }

    public Drama prepareForDistribution(Drama drama, boolean requireEnglishCover) {
        if (drama == null || drama.getId() == null || drama.getId().isBlank()) {
            return drama;
        }
        if (drama.getStatus() == DramaStatus.DISABLED || drama.getEpisodes() == null || drama.getEpisodes().isEmpty()) {
            return drama;
        }
        try {
            Drama prepared = drama;
            if (isBlank(prepared.getAiTitle())) {
                prepared = aiService.generateTitleForDistribution(drama.getId());
            }
            if (isBlank(prepared.getAiSummary())
                    || (requireEnglishCover && (isBlank(prepared.getAiTitleEn()) || isBlank(prepared.getAiSummaryEn())))) {
                prepared = aiService.generateSummary(drama.getId());
            }
            if (isBlank(prepared.getAiCoverUrl()) || isBlank(prepared.getAiVideoCoverUrl())) {
                markCoverGenerating(drama.getId(), true);
                prepared = aiService.generateCover(drama.getId());
            }
            if (requireEnglishCover && (isBlank(prepared.getAiCoverEnUrl()) || isBlank(prepared.getAiVideoCoverEnUrl()))) {
                markCoverGenerating(drama.getId(), true);
                prepared = aiService.generateEnglishCover(drama.getId());
            }
            if (isPrepared(prepared, requireEnglishCover)) {
                prepared.setStatus(DramaStatus.READY);
                prepared.setAiCoverGenerating(false);
                prepared.setAiPreparationFailedAt(null);
                return repository.save(prepared);
            }
            return prepared;
        } catch (RuntimeException exception) {
            LOGGER.warn("Baidu drama preparation failed: dramaId={}, reason={}", drama.getId(), exception.getMessage());
            markCoverGenerating(drama.getId(), false);
            drama.setAiCoverGenerating(false);
            drama.setAiPreparationFailedAt(Instant.now());
            repository.save(drama);
            return drama;
        }
    }

    private void markCoverGenerating(String dramaId, boolean generating) {
        repository.findById(dramaId).ifPresent(current -> {
            current.setAiCoverGenerating(generating);
            repository.save(current);
        });
    }

    private boolean isPrepared(Drama drama) {
        return isPrepared(drama, false);
    }

    private boolean isPrepared(Drama drama, boolean requireEnglishCover) {
        return drama != null
                && drama.getAiTitle() != null
                && !drama.getAiTitle().isBlank()
                && drama.getAiSummary() != null
                && !drama.getAiSummary().isBlank()
                && drama.getAiCoverUrl() != null
                && !drama.getAiCoverUrl().isBlank()
                && drama.getAiVideoCoverUrl() != null
                && !drama.getAiVideoCoverUrl().isBlank()
                && (!requireEnglishCover
                || (drama.getAiTitleEn() != null
                        && !drama.getAiTitleEn().isBlank()
                        && drama.getAiSummaryEn() != null
                        && !drama.getAiSummaryEn().isBlank()
                        && drama.getAiCoverEnUrl() != null
                        && !drama.getAiCoverEnUrl().isBlank()
                        && drama.getAiVideoCoverEnUrl() != null
                        && !drama.getAiVideoCoverEnUrl().isBlank()))
                && drama.getEpisodes() != null
                && !drama.getEpisodes().isEmpty();
    }

    private boolean needsPreparation(Drama drama) {
        if (drama == null || drama.getStatus() == DramaStatus.DISABLED || drama.isAiCoverGenerating()) {
            return false;
        }
        if (drama.getEpisodes() == null || drama.getEpisodes().isEmpty()) {
            return false;
        }
        if (drama.getCoverUrl() == null || drama.getCoverUrl().isBlank()) {
            return false;
        }
        if (isCoolingDown(drama)) {
            return false;
        }
        return drama.getAiTitle() == null || drama.getAiTitle().isBlank()
                || drama.getAiSummary() == null || drama.getAiSummary().isBlank()
                || drama.getAiCoverUrl() == null || drama.getAiCoverUrl().isBlank()
                || drama.getAiVideoCoverUrl() == null || drama.getAiVideoCoverUrl().isBlank();
    }

    private boolean isCoolingDown(Drama drama) {
        Instant failedAt = drama.getAiPreparationFailedAt();
        if (failedAt == null) {
            return false;
        }
        long cooldownMs = configService.get("baidu.prepareFailureCooldownMs")
                .map(BaiduDramaPreparationService::parseLong)
                .orElse(600000L);
        return cooldownMs > 0 && failedAt.plus(Duration.ofMillis(cooldownMs)).isAfter(Instant.now());
    }

    private boolean prepareOnDemandOnly() {
        return configService.get("drama.prepareOnDemandOnly")
                .map(Boolean::parseBoolean)
                .orElse(true);
    }

    private static long parseLong(String value) {
        try {
            return Long.parseLong(value.trim());
        } catch (RuntimeException exception) {
            return 600000L;
        }
    }

    private boolean isBlank(String value) {
        return value == null || value.isBlank();
    }
}
