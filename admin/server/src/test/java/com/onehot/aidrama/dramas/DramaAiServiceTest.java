package com.onehot.aidrama.dramas;

import com.onehot.aidrama.ai.AiService;
import com.onehot.aidrama.ai.AiTaskService;
import com.onehot.aidrama.common.error.BusinessException;
import com.onehot.aidrama.configs.SystemConfigService;
import com.onehot.aidrama.distribution.DistributionTaskRepository;
import org.junit.jupiter.api.Test;

import java.util.Optional;
import java.util.function.Function;
import java.util.function.Supplier;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class DramaAiServiceTest {
    private DramaAiService service(
            DramaRepository repository,
            AiService aiService,
            DramaAiCoverStorage coverStorage,
            SystemConfigService configService,
            DistributionTaskRepository taskRepository
    ) {
        AiTaskService aiTaskService = mock(AiTaskService.class);
        when(aiService.textModel()).thenReturn(AiService.DEFAULT_TEXT_MODEL);
        when(aiService.imageModel()).thenReturn(AiService.DEFAULT_IMAGE_MODEL);
        when(aiService.imageSize()).thenReturn(AiService.DEFAULT_IMAGE_SIZE);
        when(aiService.imageQuality()).thenReturn(AiService.DEFAULT_IMAGE_QUALITY);
        when(aiService.imageOutputFormat()).thenReturn(AiService.DEFAULT_IMAGE_FORMAT);
        when(aiTaskService.run(any(), any(), any())).thenAnswer(invocation -> {
            Supplier<?> call = invocation.getArgument(1);
            Function<Object, ?> responsePayload = invocation.getArgument(2);
            Object result = call.get();
            responsePayload.apply(result);
            return result;
        });
        return new DramaAiService(
                repository,
                aiService,
                coverStorage,
                configService,
                taskRepository,
                aiTaskService
        );
    }

    @Test
    void generateTitleStoresAiTitleWithoutChangingOriginalTitle() {
        DramaRepository repository = mock(DramaRepository.class);
        AiService aiService = mock(AiService.class);
        DramaAiCoverStorage coverStorage = mock(DramaAiCoverStorage.class);
        SystemConfigService configService = mock(SystemConfigService.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DramaAiService service = service(repository, aiService, coverStorage, configService, taskRepository);

        Drama drama = new Drama();
        drama.setId("drama-1");
        drama.setTitle("原始剧名");
        drama.setSummary("剧情简介");
        when(repository.findById("drama-1")).thenReturn(Optional.of(drama));
        when(repository.save(any(Drama.class))).thenAnswer(invocation -> invocation.getArgument(0));
        when(configService.get(any())).thenReturn(Optional.empty());
        when(taskRepository.existsActiveByDramaId("drama-1")).thenReturn(false);
        when(aiService.generateText(any(), any())).thenReturn("《新剧名》");

        Drama updated = service.generateTitle("drama-1");

        assertThat(updated.getTitle()).isEqualTo("原始剧名");
        assertThat(updated.getAiTitle()).isEqualTo("新剧名");
    }

    @Test
    void generateTitleDefaultPromptKeepsOriginalStyleAndAvoidsViolentWording() {
        DramaRepository repository = mock(DramaRepository.class);
        AiService aiService = mock(AiService.class);
        DramaAiCoverStorage coverStorage = mock(DramaAiCoverStorage.class);
        SystemConfigService configService = mock(SystemConfigService.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DramaAiService service = service(repository, aiService, coverStorage, configService, taskRepository);

        Drama drama = new Drama();
        drama.setId("drama-1");
        drama.setTitle("一念情深一念仇");
        drama.setSummary("曾经明艳动人的妹妹归来，旧情与误会交织。");
        when(repository.findById("drama-1")).thenReturn(Optional.of(drama));
        when(repository.save(any(Drama.class))).thenAnswer(invocation -> invocation.getArgument(0));
        when(configService.get(any())).thenReturn(Optional.empty());
        when(taskRepository.existsActiveByDramaId("drama-1")).thenReturn(false);
        when(aiService.generateText(any(), any())).thenReturn("妹妹的眼泪");

        service.generateTitle("drama-1");

        verify(aiService).generateText(
                org.mockito.ArgumentMatchers.argThat(prompt ->
                        prompt.contains("延续原始剧名的风格")
                                && prompt.contains("不要把温柔、美感、情感向的原题改成血腥暴力")
                                && prompt.contains("灭门")
                                && prompt.contains("血洗")
                ),
                any()
        );
    }

    @Test
    void generateTitleRejectsDramaThatHasActiveDistributionTask() {
        DramaRepository repository = mock(DramaRepository.class);
        AiService aiService = mock(AiService.class);
        DramaAiCoverStorage coverStorage = mock(DramaAiCoverStorage.class);
        SystemConfigService configService = mock(SystemConfigService.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DramaAiService service = service(repository, aiService, coverStorage, configService, taskRepository);

        Drama drama = new Drama();
        drama.setId("drama-1");
        drama.setTitle("原始剧名");
        when(repository.findById("drama-1")).thenReturn(Optional.of(drama));
        when(taskRepository.existsActiveByDramaId("drama-1")).thenReturn(true);

        assertThatThrownBy(() -> service.generateTitle("drama-1"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("已经分发");
        verify(aiService, never()).generateText(any(), any());
        verify(repository, never()).save(any(Drama.class));
    }

    @Test
    void generateCoverStoresAiCoverUrlWithoutChangingOriginalCover() {
        DramaRepository repository = mock(DramaRepository.class);
        AiService aiService = mock(AiService.class);
        DramaAiCoverStorage coverStorage = mock(DramaAiCoverStorage.class);
        SystemConfigService configService = mock(SystemConfigService.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DramaAiService service = service(repository, aiService, coverStorage, configService, taskRepository);

        Drama drama = new Drama();
        drama.setId("drama-1");
        drama.setTitle("原始剧名");
        drama.setCoverUrl("/uploads/covers/source.jpg");
        drama.setAiCoverGenerating(true);
        when(repository.findById("drama-1")).thenReturn(Optional.of(drama));
        when(repository.save(any(Drama.class))).thenAnswer(invocation -> invocation.getArgument(0));
        when(configService.get(any())).thenReturn(Optional.empty());
        when(aiService.generateImageBase64(any())).thenReturn("aW1hZ2U=");
        when(coverStorage.store(eq("aW1hZ2U="), eq("jpeg"))).thenReturn("/uploads/ai-covers/new.jpg");

        Drama updated = service.generateCover("drama-1");

        assertThat(updated.getCoverUrl()).isEqualTo("/uploads/covers/source.jpg");
        assertThat(updated.getAiCoverUrl()).isEqualTo("/uploads/ai-covers/new.jpg");
        assertThat(updated.isAiCoverGenerating()).isFalse();
    }

    @Test
    void generateCoverPromptUsesAiTitleAndKeepsBeautifulNonViolentHook() {
        DramaRepository repository = mock(DramaRepository.class);
        AiService aiService = mock(AiService.class);
        DramaAiCoverStorage coverStorage = mock(DramaAiCoverStorage.class);
        SystemConfigService configService = mock(SystemConfigService.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DramaAiService service = service(repository, aiService, coverStorage, configService, taskRepository);

        Drama drama = new Drama();
        drama.setId("drama-1");
        drama.setTitle("一念情深一念仇");
        drama.setAiTitle("妹妹的眼泪");
        drama.setSummary("曾经明艳动人的妹妹归来，旧情与误会交织。");
        when(repository.findById("drama-1")).thenReturn(Optional.of(drama));
        when(repository.save(any(Drama.class))).thenAnswer(invocation -> invocation.getArgument(0));
        when(configService.get(any())).thenReturn(Optional.empty());
        when(aiService.generateImageBase64(any())).thenReturn("aW1hZ2U=");
        when(coverStorage.store(any(), any())).thenReturn("/uploads/ai-covers/new.jpg");

        service.generateCover("drama-1");

        verify(aiService).generateImageBase64(org.mockito.ArgumentMatchers.argThat(prompt ->
                prompt.contains("封面剧名：妹妹的眼泪")
                        && prompt.contains("保持美感")
                        && prompt.contains("不要出现血腥、暴力")
                        && prompt.contains("看点")
                        && prompt.contains("不要出现原始剧名")
                        && !prompt.contains("原始剧名：")
                        && !prompt.contains("一念情深一念仇")
                        && !prompt.contains("封面剧名：一念情深一念仇")
        ));
    }
}
