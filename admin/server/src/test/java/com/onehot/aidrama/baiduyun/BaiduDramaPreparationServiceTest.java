package com.onehot.aidrama.baiduyun;

import com.onehot.aidrama.dramas.Drama;
import com.onehot.aidrama.dramas.DramaAiService;
import com.onehot.aidrama.dramas.DramaEpisode;
import com.onehot.aidrama.dramas.DramaRepository;
import com.onehot.aidrama.dramas.DramaStatus;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class BaiduDramaPreparationServiceTest {
    @Test
    void marksDramaReadyOnlyAfterTitleAndCoverGenerationSucceed() {
        DramaRepository repository = mock(DramaRepository.class);
        DramaAiService aiService = mock(DramaAiService.class);
        BaiduDramaPreparationService service = new BaiduDramaPreparationService(repository, aiService);
        Drama drama = drama("drama-1");
        drama.setStatus(DramaStatus.DRAFT);
        Drama titled = drama("drama-1");
        titled.setAiTitle("新剧名");
        Drama covered = drama("drama-1");
        covered.setAiTitle("新剧名");
        covered.setAiCoverUrl("/uploads/ai-covers/new.jpg");
        when(aiService.generateTitle("drama-1")).thenReturn(titled);
        when(aiService.generateCover("drama-1")).thenReturn(covered);
        when(repository.save(org.mockito.ArgumentMatchers.any(Drama.class))).thenAnswer(invocation -> invocation.getArgument(0));

        Drama prepared = service.prepareForDistribution(drama);

        assertThat(prepared.getStatus()).isEqualTo(DramaStatus.READY);
        assertThat(prepared.isAiCoverGenerating()).isFalse();
        verify(aiService).generateTitle("drama-1");
        verify(aiService).generateCover("drama-1");
        verify(repository).save(org.mockito.ArgumentMatchers.argThat(saved -> saved.getStatus() == DramaStatus.READY));
    }

    @Test
    void keepsDramaDraftWhenAiCoverGenerationFails() {
        DramaRepository repository = mock(DramaRepository.class);
        DramaAiService aiService = mock(DramaAiService.class);
        BaiduDramaPreparationService service = new BaiduDramaPreparationService(repository, aiService);
        Drama drama = drama("drama-1");
        drama.setStatus(DramaStatus.DRAFT);
        Drama titled = drama("drama-1");
        titled.setAiTitle("新剧名");
        when(aiService.generateTitle("drama-1")).thenReturn(titled);
        when(aiService.generateCover("drama-1")).thenThrow(new IllegalStateException("image failed"));
        when(repository.save(org.mockito.ArgumentMatchers.any(Drama.class))).thenAnswer(invocation -> invocation.getArgument(0));

        Drama prepared = service.prepareForDistribution(drama);

        assertThat(prepared.getStatus()).isEqualTo(DramaStatus.DRAFT);
        assertThat(prepared.isAiCoverGenerating()).isFalse();
    }

    private Drama drama(String id) {
        Drama drama = new Drama();
        drama.setId(id);
        drama.setTitle("原始剧名");
        DramaEpisode episode = new DramaEpisode();
        episode.setEpisodeNo(1);
        episode.setSourcePath("/root/01.mp4");
        drama.setEpisodes(List.of(episode));
        return drama;
    }
}
