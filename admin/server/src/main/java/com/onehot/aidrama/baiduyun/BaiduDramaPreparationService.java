package com.onehot.aidrama.baiduyun;

import com.onehot.aidrama.dramas.Drama;
import com.onehot.aidrama.dramas.DramaAiService;
import com.onehot.aidrama.dramas.DramaRepository;
import com.onehot.aidrama.dramas.DramaStatus;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class BaiduDramaPreparationService {
    private static final Logger LOGGER = LoggerFactory.getLogger(BaiduDramaPreparationService.class);

    private final DramaRepository repository;
    private final DramaAiService aiService;

    public BaiduDramaPreparationService(DramaRepository repository, DramaAiService aiService) {
        this.repository = repository;
        this.aiService = aiService;
    }

    public Drama prepareForDistribution(Drama drama) {
        if (drama == null || drama.getId() == null || drama.getId().isBlank()) {
            return drama;
        }
        if (drama.getStatus() == DramaStatus.DISABLED || drama.getEpisodes() == null || drama.getEpisodes().isEmpty()) {
            return drama;
        }
        try {
            aiService.generateTitle(drama.getId());
            markCoverGenerating(drama.getId(), true);
            Drama prepared = aiService.generateCover(drama.getId());
            if (isPrepared(prepared)) {
                prepared.setStatus(DramaStatus.READY);
                prepared.setAiCoverGenerating(false);
                return repository.save(prepared);
            }
            return prepared;
        } catch (RuntimeException exception) {
            LOGGER.warn("Baidu drama preparation failed: dramaId={}, reason={}", drama.getId(), exception.getMessage());
            markCoverGenerating(drama.getId(), false);
            drama.setAiCoverGenerating(false);
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
        return drama != null
                && drama.getAiTitle() != null
                && !drama.getAiTitle().isBlank()
                && drama.getAiCoverUrl() != null
                && !drama.getAiCoverUrl().isBlank()
                && drama.getEpisodes() != null
                && !drama.getEpisodes().isEmpty();
    }
}
