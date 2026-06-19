package com.onehot.aidrama.baiduyun;

import com.onehot.aidrama.dramas.Drama;
import com.onehot.aidrama.dramas.DramaAiService;
import com.onehot.aidrama.dramas.DramaEpisode;
import com.onehot.aidrama.dramas.DramaRepository;
import com.onehot.aidrama.dramas.DramaStatus;
import com.onehot.aidrama.configs.SystemConfigService;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class BaiduDramaPreparationServiceTest {
    @Test
    void marksDramaReadyOnlyAfterTitleAndCoverGenerationSucceed() {
        DramaRepository repository = mock(DramaRepository.class);
        DramaAiService aiService = mock(DramaAiService.class);
        BaiduDramaPreparationService service = service(repository, aiService);
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
        BaiduDramaPreparationService service = service(repository, aiService);
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
        assertThat(prepared.getAiPreparationFailedAt()).isNotNull();
    }

    @Test
    void scheduledPreparationProcessesOnePendingDramaWithOriginalCover() {
        DramaRepository repository = mock(DramaRepository.class);
        DramaAiService aiService = mock(DramaAiService.class);
        BaiduDramaPreparationService service = service(repository, aiService);
        Drama noCover = drama("no-cover");
        Drama ready = drama("ready");
        ready.setCoverUrl("/uploads/covers/original.jpg");
        ready.setAiTitle("已有剧名");
        ready.setAiCoverUrl("/uploads/ai-covers/existing.jpg");
        Drama pending = drama("pending");
        pending.setCoverUrl("/uploads/covers/original.jpg");
        Drama titled = drama("pending");
        titled.setCoverUrl("/uploads/covers/original.jpg");
        titled.setAiTitle("新剧名");
        Drama covered = drama("pending");
        covered.setCoverUrl("/uploads/covers/original.jpg");
        covered.setAiTitle("新剧名");
        covered.setAiCoverUrl("/uploads/ai-covers/new.jpg");
        when(repository.findAll()).thenReturn(List.of(noCover, ready, pending));
        when(repository.findById("pending")).thenReturn(Optional.of(pending));
        when(aiService.generateTitle("pending")).thenReturn(titled);
        when(aiService.generateCover("pending")).thenReturn(covered);
        when(repository.save(org.mockito.ArgumentMatchers.any(Drama.class))).thenAnswer(invocation -> invocation.getArgument(0));

        Optional<Drama> prepared = service.prepareNextPendingDrama();

        assertThat(prepared).contains(covered);
        verify(aiService).generateTitle("pending");
        verify(aiService).generateCover("pending");
        verify(aiService, never()).generateTitle("no-cover");
        verify(aiService, never()).generateTitle("ready");
    }

    @Test
    void preparationDoesNotRegenerateExistingAiTitle() {
        DramaRepository repository = mock(DramaRepository.class);
        DramaAiService aiService = mock(DramaAiService.class);
        BaiduDramaPreparationService service = service(repository, aiService);
        Drama drama = drama("drama-1");
        drama.setCoverUrl("/uploads/covers/original.jpg");
        drama.setAiTitle("已有剧名");
        Drama covered = drama("drama-1");
        covered.setCoverUrl("/uploads/covers/original.jpg");
        covered.setAiTitle("已有剧名");
        covered.setAiCoverUrl("/uploads/ai-covers/new.jpg");
        when(aiService.generateCover("drama-1")).thenReturn(covered);
        when(repository.save(org.mockito.ArgumentMatchers.any(Drama.class))).thenAnswer(invocation -> invocation.getArgument(0));

        Drama prepared = service.prepareForDistribution(drama);

        assertThat(prepared.getStatus()).isEqualTo(DramaStatus.READY);
        verify(aiService, never()).generateTitle("drama-1");
        verify(aiService).generateCover("drama-1");
    }

    @Test
    void skipsDramaDuringPreparationFailureCooldown() {
        DramaRepository repository = mock(DramaRepository.class);
        DramaAiService aiService = mock(DramaAiService.class);
        SystemConfigService configService = mock(SystemConfigService.class);
        BaiduDramaPreparationService service = new BaiduDramaPreparationService(repository, aiService, configService);
        Drama coolingDown = drama("cooling-down");
        coolingDown.setCoverUrl("/uploads/covers/original.jpg");
        coolingDown.setAiPreparationFailedAt(Instant.now());
        when(repository.findAll()).thenReturn(List.of(coolingDown));
        when(configService.get("baidu.prepareFailureCooldownMs")).thenReturn(Optional.of("600000"));

        Optional<Drama> prepared = service.prepareNextPendingDrama();

        assertThat(prepared).isEmpty();
        verify(aiService, never()).generateTitle("cooling-down");
        verify(aiService, never()).generateCover("cooling-down");
    }

    private BaiduDramaPreparationService service(DramaRepository repository, DramaAiService aiService) {
        SystemConfigService configService = mock(SystemConfigService.class);
        when(configService.get("baidu.prepareFailureCooldownMs")).thenReturn(Optional.empty());
        return new BaiduDramaPreparationService(repository, aiService, configService);
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
