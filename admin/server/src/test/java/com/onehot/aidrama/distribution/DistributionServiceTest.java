package com.onehot.aidrama.distribution;

import com.onehot.aidrama.baiduyun.BaiduDramaPreparationService;
import com.onehot.aidrama.dramas.Drama;
import com.onehot.aidrama.dramas.DramaEpisode;
import com.onehot.aidrama.dramas.DramaRepository;
import com.onehot.aidrama.dramas.DramaSources;
import com.onehot.aidrama.dramas.DramaStatus;
import com.onehot.aidrama.media.DistributionPolicy;
import com.onehot.aidrama.media.MediaAccount;
import com.onehot.aidrama.media.MediaAccountRepository;
import com.onehot.aidrama.media.MediaAccountStatus;
import com.onehot.aidrama.media.MediaPlatform;
import com.onehot.aidrama.common.PageResult;
import com.onehot.aidrama.users.Account;
import com.onehot.aidrama.users.AccountRepository;
import org.junit.jupiter.api.Test;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.test.util.ReflectionTestUtils;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class DistributionServiceTest {
    @Test
    void preparesAndClaimsExistingTaskForCurrentOwnerWithoutGeneratingQueue() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        MediaAccount owned = new MediaAccount();
        owned.setId("media-owned");
        owned.setOwnerAccountId("owner-1");
        owned.setStatus(MediaAccountStatus.ACTIVE);
        DistributionPolicy policy = new DistributionPolicy();
        policy.setEnabled(true);
        policy.setCategoryIds(List.of("urban"));
        owned.setDistributionPolicy(policy);

        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(owned));
        when(taskRepository.save(any(DistributionTask.class))).thenAnswer(invocation -> invocation.getArgument(0));
        when(taskRepository.findFirstByStatusAndMediaAccountIdInOrderByPriorityDescCreatedAtAsc(
                DistributionTaskStatus.PENDING,
                List.of("media-owned")
        )).thenAnswer(invocation -> {
            DistributionTask task = new DistributionTask();
            task.setMediaAccountId("media-owned");
            task.setDramaId("drama-1");
            task.setStatus(DistributionTaskStatus.PENDING);
            return Optional.of(task);
        });

        Optional<DistributionTask> claimed = service.prepareAndClaimForOwner("owner-1", "device-1");

        assertThat(claimed).isPresent();
        assertThat(claimed.get().getMediaAccountId()).isEqualTo("media-owned");
        assertThat(claimed.get().getLockedByDeviceId()).isEqualTo("device-1");
        assertThat(claimed.get().getStatus()).isEqualTo(DistributionTaskStatus.CLAIMED);
        verify(dramaRepository, never()).findByStatusInAndCreatedAtGreaterThanEqual(
                any(),
                any(Instant.class),
                any(Sort.class)
        );
        verify(dramaRepository, never()).findByStatus(DramaStatus.READY);
    }

    @Test
    void claimRejectsWhenDailyPublishLimitReached() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        when(mediaAccountRepository.findByOwnerAccountId("owner-1"))
                .thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.countByMediaAccountIdInAndUpdatedAtGreaterThanEqualAndStatusIn(
                eq(List.of("media-1")),
                any(Instant.class),
                any()
        )).thenReturn(10L);

        assertThatThrownBy(() -> service.claimForOwner("owner-1", "device-1", true))
                .hasMessageContaining("今日发布次数已达 10 次");

        verify(taskRepository, never()).findFirstByStatusAndMediaAccountIdInOrderByPriorityDescCreatedAtAsc(any(), any());
        verify(taskRepository, never()).save(any(DistributionTask.class));
    }

    @Test
    void claimUsesSeparateDailyPublishLimitByPlatform() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        MediaAccount wechat = activeMedia("media-wechat", "owner-1", "urban", MediaPlatform.WECHAT_VIDEO);
        MediaAccount tiktok = activeMedia("media-tiktok", "owner-1", "urban", MediaPlatform.TIKTOK);
        DistributionTask pendingTiktok = new DistributionTask();
        pendingTiktok.setMediaAccountId("media-tiktok");
        pendingTiktok.setDramaId("drama-1");
        pendingTiktok.setStatus(DistributionTaskStatus.PENDING);

        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(wechat, tiktok));
        when(taskRepository.countByMediaAccountIdInAndUpdatedAtGreaterThanEqualAndStatusIn(
                eq(List.of("media-wechat")),
                any(Instant.class),
                any()
        )).thenReturn(10L);
        when(taskRepository.countByMediaAccountIdInAndUpdatedAtGreaterThanEqualAndStatusIn(
                eq(List.of("media-tiktok")),
                any(Instant.class),
                any()
        )).thenReturn(0L);
        when(taskRepository.findFirstByStatusAndMediaAccountIdInOrderByPriorityDescCreatedAtAsc(
                DistributionTaskStatus.PENDING,
                List.of("media-tiktok")
        )).thenReturn(Optional.of(pendingTiktok));
        when(mediaAccountRepository.findById("media-tiktok")).thenReturn(Optional.of(tiktok));
        when(taskRepository.save(pendingTiktok)).thenReturn(pendingTiktok);

        Optional<DistributionTask> claimed = service.claimForOwner("owner-1", "device-1", true);

        assertThat(claimed).contains(pendingTiktok);
        assertThat(claimed.get().getPlatform()).isEqualTo(MediaPlatform.TIKTOK);
        verify(taskRepository).findFirstByStatusAndMediaAccountIdInOrderByPriorityDescCreatedAtAsc(
                DistributionTaskStatus.PENDING,
                List.of("media-tiktok")
        );
    }

    @Test
    void claimIgnoresPausedMediaAccounts() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        MediaAccount pausedWechat = activeMedia("media-wechat", "owner-1", "urban", MediaPlatform.WECHAT_VIDEO);
        pausedWechat.setStatus(MediaAccountStatus.PAUSED);
        MediaAccount activeTiktok = activeMedia("media-tiktok", "owner-1", "urban", MediaPlatform.TIKTOK);
        DistributionTask pendingTiktok = new DistributionTask();
        pendingTiktok.setMediaAccountId("media-tiktok");
        pendingTiktok.setDramaId("drama-1");
        pendingTiktok.setStatus(DistributionTaskStatus.PENDING);

        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(pausedWechat, activeTiktok));
        when(taskRepository.findFirstByStatusAndMediaAccountIdInOrderByPriorityDescCreatedAtAsc(
                DistributionTaskStatus.PENDING,
                List.of("media-tiktok")
        )).thenReturn(Optional.of(pendingTiktok));
        when(taskRepository.save(pendingTiktok)).thenReturn(pendingTiktok);

        Optional<DistributionTask> claimed = service.claimForOwner("owner-1", "device-1", true);

        assertThat(claimed).contains(pendingTiktok);
        assertThat(claimed.get().getMediaAccountId()).isEqualTo("media-tiktok");
        verify(taskRepository).findFirstByStatusAndMediaAccountIdInOrderByPriorityDescCreatedAtAsc(
                DistributionTaskStatus.PENDING,
                List.of("media-tiktok")
        );
    }

    @Test
    void claimPreparesAiAssetsBeforeReturningTask() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        BaiduDramaPreparationService preparationService = mock(BaiduDramaPreparationService.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository, preparationService);

        DistributionTask pending = new DistributionTask();
        pending.setId("task-1");
        pending.setMediaAccountId("media-1");
        pending.setDramaId("drama-1");
        pending.setStatus(DistributionTaskStatus.PENDING);
        Drama drama = readyDrama("drama-1", "urban");
        drama.setAiTitle(null);
        drama.setAiSummary(null);
        drama.setAiCoverUrl(null);
        drama.setAiVideoCoverUrl(null);
        Drama prepared = readyDrama("drama-1", "urban");

        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.findFirstByStatusAndMediaAccountIdInOrderByPriorityDescCreatedAtAsc(
                DistributionTaskStatus.PENDING,
                List.of("media-1")
        )).thenReturn(Optional.of(pending));
        when(dramaRepository.findById("drama-1")).thenReturn(Optional.of(drama));
        when(preparationService.prepareForDistribution(drama)).thenReturn(prepared);
        when(taskRepository.save(pending)).thenReturn(pending);

        Optional<DistributionTask> claimed = service.claimForOwner("owner-1", "device-1");

        assertThat(claimed).contains(pending);
        assertThat(pending.getStatus()).isEqualTo(DistributionTaskStatus.CLAIMED);
        assertThat(pending.getLockedByDeviceId()).isEqualTo("device-1");
        verify(preparationService).prepareForDistribution(drama);
    }

    @Test
    void asyncClaimReturnsTaskBeforeAiPreparation() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        BaiduDramaPreparationService preparationService = mock(BaiduDramaPreparationService.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository, preparationService);

        DistributionTask pending = new DistributionTask();
        pending.setId("task-1");
        pending.setMediaAccountId("media-1");
        pending.setDramaId("drama-1");
        pending.setStatus(DistributionTaskStatus.PENDING);

        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.findFirstByStatusAndMediaAccountIdInOrderByPriorityDescCreatedAtAsc(
                DistributionTaskStatus.PENDING,
                List.of("media-1")
        )).thenReturn(Optional.of(pending));
        when(taskRepository.save(pending)).thenReturn(pending);

        Optional<DistributionTask> claimed = service.claimForOwner("owner-1", "device-1", true);

        assertThat(claimed).contains(pending);
        assertThat(pending.getStatus()).isEqualTo(DistributionTaskStatus.CLAIMED);
        assertThat(pending.getLockedByDeviceId()).isEqualTo("device-1");
        verify(dramaRepository, never()).findById("drama-1");
        verify(preparationService, never()).prepareForDistribution(any());
    }

    @Test
    void asyncPreparationEndpointStartsPreparationAndLaterReportsReady() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        BaiduDramaPreparationService preparationService = mock(BaiduDramaPreparationService.class);
        DistributionService service = new DistributionService(
                dramaRepository,
                mediaAccountRepository,
                taskRepository,
                preparationService,
                Runnable::run
        );

        DistributionTask task = new DistributionTask();
        task.setId("task-1");
        task.setMediaAccountId("media-1");
        task.setDramaId("drama-1");
        task.setStatus(DistributionTaskStatus.CLAIMED);
        Drama unprepared = readyDrama("drama-1", "urban");
        unprepared.setAiTitle(null);
        unprepared.setAiSummary(null);
        unprepared.setAiCoverUrl(null);
        unprepared.setAiVideoCoverUrl(null);
        Drama prepared = readyDrama("drama-1", "urban");

        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.findById("task-1")).thenReturn(Optional.of(task));
        when(dramaRepository.findById("drama-1")).thenReturn(Optional.of(unprepared), Optional.of(unprepared), Optional.of(prepared));
        when(preparationService.prepareForDistribution(unprepared)).thenReturn(prepared);

        DistributionDtos.PreparationResponse first = service.prepareTaskDramaForOwner("owner-1", "task-1");
        DistributionDtos.PreparationResponse second = service.prepareTaskDramaForOwner("owner-1", "task-1");

        assertThat(first.preparing()).isTrue();
        assertThat(second.prepared()).isTrue();
        verify(preparationService).prepareForDistribution(unprepared);
    }

    @Test
    void tiktokPreparationEndpointRequiresEnglishAssets() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        BaiduDramaPreparationService preparationService = mock(BaiduDramaPreparationService.class);
        DistributionService service = new DistributionService(
                dramaRepository,
                mediaAccountRepository,
                taskRepository,
                preparationService,
                Runnable::run
        );

        DistributionTask task = new DistributionTask();
        task.setId("task-1");
        task.setMediaAccountId("media-tiktok");
        task.setPlatform(MediaPlatform.TIKTOK);
        task.setDramaId("drama-1");
        task.setStatus(DistributionTaskStatus.CLAIMED);
        Drama unprepared = readyDrama("drama-1", "urban");
        Drama prepared = readyDrama("drama-1", "urban");
        markTiktokPrepared(prepared);

        when(mediaAccountRepository.findByOwnerAccountId("owner-1"))
                .thenReturn(List.of(activeMedia("media-tiktok", "owner-1", "urban", MediaPlatform.TIKTOK)));
        when(taskRepository.findById("task-1")).thenReturn(Optional.of(task));
        when(dramaRepository.findById("drama-1")).thenReturn(Optional.of(unprepared), Optional.of(unprepared), Optional.of(prepared));
        when(preparationService.prepareForDistribution(unprepared, true)).thenReturn(prepared);

        DistributionDtos.PreparationResponse response = service.prepareTaskDramaForOwner("owner-1", "task-1");

        assertThat(response.preparing()).isTrue();
        verify(preparationService).prepareForDistribution(unprepared, true);
        verify(preparationService, never()).prepareForDistribution(unprepared);
    }

    @Test
    void claimMarksTaskFailedWhenAiPreparationFails() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        BaiduDramaPreparationService preparationService = mock(BaiduDramaPreparationService.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository, preparationService);

        DistributionTask pending = new DistributionTask();
        pending.setId("task-1");
        pending.setMediaAccountId("media-1");
        pending.setDramaId("drama-1");
        pending.setStatus(DistributionTaskStatus.PENDING);
        Drama drama = readyDrama("drama-1", "urban");
        drama.setAiTitle(null);
        drama.setAiSummary(null);
        drama.setAiCoverUrl(null);
        drama.setAiVideoCoverUrl(null);

        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.findFirstByStatusAndMediaAccountIdInOrderByPriorityDescCreatedAtAsc(
                DistributionTaskStatus.PENDING,
                List.of("media-1")
        )).thenReturn(Optional.of(pending));
        when(dramaRepository.findById("drama-1")).thenReturn(Optional.of(drama));
        when(preparationService.prepareForDistribution(drama)).thenReturn(drama);
        when(taskRepository.save(pending)).thenReturn(pending);

        assertThatThrownBy(() -> service.claimForOwner("owner-1", "device-1"))
                .hasMessageContaining("AI 剧名、AI 简介、AI 封面或视频封面生成失败");

        assertThat(pending.getStatus()).isEqualTo(DistributionTaskStatus.FAILED);
        assertThat(pending.getFailureReason()).contains("AI 素材生成失败");
        assertThat(pending.getFinishedAt()).isNotNull();
        verify(taskRepository).save(pending);
    }

    @Test
    void prepareGeneratesOnlyOneTaskWhenNoPendingTaskExists() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        Drama firstDrama = readyDrama("drama-1", "urban");
        Drama secondDrama = readyDrama("drama-2", "urban");
        MediaAccount firstMedia = activeMedia("media-1", "owner-1", "urban");
        MediaAccount secondMedia = activeMedia("media-2", "owner-1", "urban");

        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(firstMedia, secondMedia));
        when(taskRepository.findFirstByStatusAndMediaAccountIdInOrderByPriorityDescCreatedAtAsc(
                DistributionTaskStatus.PENDING,
                List.of("media-1", "media-2")
        )).thenReturn(Optional.empty());
        when(dramaRepository.findByStatusInAndCreatedAtGreaterThanEqual(
                any(),
                any(Instant.class),
                any(Sort.class)
        )).thenReturn(List.of(firstDrama, secondDrama));
        when(taskRepository.existsByMediaAccountIdAndDramaId("media-1", "drama-1")).thenReturn(false);
        when(taskRepository.save(any(DistributionTask.class))).thenAnswer(invocation -> invocation.getArgument(0));

        Optional<DistributionTask> claimed = service.prepareAndClaimForOwner("owner-1", "device-1");

        assertThat(claimed).isPresent();
        assertThat(claimed.get().getDramaId()).isEqualTo("drama-1");
        assertThat(claimed.get().getMediaAccountId()).isEqualTo("media-1");
        assertThat(claimed.get().getStatus()).isEqualTo(DistributionTaskStatus.CLAIMED);
        assertThat(claimed.get().getLockedByDeviceId()).isEqualTo("device-1");
        verify(taskRepository, times(2)).save(any(DistributionTask.class));
        verify(taskRepository, never()).existsByMediaAccountIdAndDramaId("media-2", "drama-1");
        verify(taskRepository, never()).existsByMediaAccountIdAndDramaId("media-1", "drama-2");
    }

    @Test
    void generatesOneTaskPerPlatformWhenMultipleEligibleMediaAccountsSharePlatform() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        Drama drama = new Drama();
        drama.setId("drama-1");
        drama.setStatus(DramaStatus.READY);
        drama.setCategoryIds(List.of("urban"));
        markCreatedNow(drama);
        DramaEpisode episode = new DramaEpisode();
        episode.setEpisodeNo(1);
        episode.setSourcePath("/drama/1.mp4");
        drama.setEpisodes(List.of(episode));
        markPrepared(drama);

        MediaAccount first = activeMedia("media-1", "owner-1", "urban");
        MediaAccount second = activeMedia("media-2", "owner-1", "urban");

        when(dramaRepository.findByStatusInAndCreatedAtGreaterThanEqual(
                any(),
                any(Instant.class),
                any(Sort.class)
        )).thenReturn(List.of(drama));
        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(first, second));
        when(taskRepository.existsByMediaAccountIdAndDramaId("media-1", "drama-1")).thenReturn(false);
        when(taskRepository.existsByMediaAccountIdAndDramaId("media-2", "drama-1")).thenReturn(false);
        when(taskRepository.save(any(DistributionTask.class))).thenAnswer(invocation -> invocation.getArgument(0));

        List<DistributionTask> generated = service.generateTasksForOwner("owner-1");

        assertThat(generated).hasSize(1);
        assertThat(generated).extracting(DistributionTask::getDramaId).containsOnly("drama-1");
        assertThat(generated).extracting(DistributionTask::getMediaAccountId).containsExactly("media-1");
        assertThat(generated).extracting(DistributionTask::getPlatform).containsExactly(MediaPlatform.WECHAT_VIDEO);
        verify(taskRepository).save(any(DistributionTask.class));
    }

    @Test
    void generatesOneTaskForWechatAndOneTaskForTiktokForSameDrama() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        Drama drama = readyDrama("drama-1", "urban");
        MediaAccount wechat = activeMedia("media-wechat", "owner-1", "urban", MediaPlatform.WECHAT_VIDEO);
        MediaAccount anotherWechat = activeMedia("media-wechat-2", "owner-1", "urban", MediaPlatform.WECHAT_VIDEO);
        MediaAccount tiktok = activeMedia("media-tiktok", "owner-1", "urban", MediaPlatform.TIKTOK);

        when(dramaRepository.findByStatusInAndCreatedAtGreaterThanEqual(
                any(),
                any(Instant.class),
                any(Sort.class)
        )).thenReturn(List.of(drama));
        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(wechat, anotherWechat, tiktok));
        when(taskRepository.existsByMediaAccountIdAndDramaId(any(), eq("drama-1"))).thenReturn(false);
        when(taskRepository.existsByDramaIdAndPlatform(eq("drama-1"), any())).thenReturn(false);
        when(taskRepository.save(any(DistributionTask.class))).thenAnswer(invocation -> invocation.getArgument(0));

        List<DistributionTask> generated = service.generateTasksForOwner("owner-1");

        assertThat(generated).hasSize(2);
        assertThat(generated).extracting(DistributionTask::getMediaAccountId).containsExactly("media-wechat", "media-tiktok");
        assertThat(generated).extracting(DistributionTask::getPlatform).containsExactly(MediaPlatform.WECHAT_VIDEO, MediaPlatform.TIKTOK);
        verify(taskRepository, times(2)).save(any(DistributionTask.class));
    }

    @Test
    void prepareNextCreatesTiktokTaskWhenWechatTaskAlreadyExistsForSameDrama() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        Drama drama = readyDrama("drama-1", "urban");
        MediaAccount wechat = activeMedia("media-wechat", "owner-1", "urban", MediaPlatform.WECHAT_VIDEO);
        MediaAccount tiktok = activeMedia("media-tiktok", "owner-1", "urban", MediaPlatform.TIKTOK);

        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(wechat, tiktok));
        when(taskRepository.findFirstByStatusAndMediaAccountIdInOrderByPriorityDescCreatedAtAsc(
                DistributionTaskStatus.PENDING,
                List.of("media-wechat", "media-tiktok")
        )).thenReturn(Optional.empty());
        when(dramaRepository.findByStatusInAndCreatedAtGreaterThanEqual(
                any(),
                any(Instant.class),
                any(Sort.class)
        )).thenReturn(List.of(drama));
        when(taskRepository.existsByMediaAccountIdAndDramaId("media-wechat", "drama-1")).thenReturn(true);
        when(taskRepository.existsByMediaAccountIdAndDramaId("media-tiktok", "drama-1")).thenReturn(false);
        when(taskRepository.existsByDramaIdAndPlatform("drama-1", MediaPlatform.TIKTOK)).thenReturn(false);
        when(taskRepository.save(any(DistributionTask.class))).thenAnswer(invocation -> invocation.getArgument(0));

        Optional<DistributionTask> claimed = service.prepareAndClaimForOwner("owner-1", "device-1", true);

        assertThat(claimed).isPresent();
        assertThat(claimed.get().getMediaAccountId()).isEqualTo("media-tiktok");
        assertThat(claimed.get().getPlatform()).isEqualTo(MediaPlatform.TIKTOK);
        assertThat(claimed.get().getStatus()).isEqualTo(DistributionTaskStatus.CLAIMED);
    }

    @Test
    void prepareNextUsesSeparateDailyPublishLimitByPlatform() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        Drama drama = readyDrama("drama-1", "urban");
        MediaAccount wechat = activeMedia("media-wechat", "owner-1", "urban", MediaPlatform.WECHAT_VIDEO);
        MediaAccount tiktok = activeMedia("media-tiktok", "owner-1", "urban", MediaPlatform.TIKTOK);

        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(wechat, tiktok));
        when(taskRepository.countByMediaAccountIdInAndUpdatedAtGreaterThanEqualAndStatusIn(
                eq(List.of("media-wechat")),
                any(Instant.class),
                any()
        )).thenReturn(10L);
        when(taskRepository.countByMediaAccountIdInAndUpdatedAtGreaterThanEqualAndStatusIn(
                eq(List.of("media-tiktok")),
                any(Instant.class),
                any()
        )).thenReturn(0L);
        when(taskRepository.findFirstByStatusAndMediaAccountIdInOrderByPriorityDescCreatedAtAsc(
                DistributionTaskStatus.PENDING,
                List.of("media-tiktok")
        )).thenReturn(Optional.empty());
        when(dramaRepository.findByStatusInAndCreatedAtGreaterThanEqual(
                any(),
                any(Instant.class),
                any(Sort.class)
        )).thenReturn(List.of(drama));
        when(taskRepository.existsByMediaAccountIdAndDramaId("media-tiktok", "drama-1")).thenReturn(false);
        when(taskRepository.existsByDramaIdAndPlatform("drama-1", MediaPlatform.TIKTOK)).thenReturn(false);
        when(taskRepository.save(any(DistributionTask.class))).thenAnswer(invocation -> invocation.getArgument(0));

        Optional<DistributionTask> claimed = service.prepareAndClaimForOwner("owner-1", "device-1", true);

        assertThat(claimed).isPresent();
        assertThat(claimed.get().getMediaAccountId()).isEqualTo("media-tiktok");
        assertThat(claimed.get().getPlatform()).isEqualTo(MediaPlatform.TIKTOK);
        assertThat(claimed.get().getStatus()).isEqualTo(DistributionTaskStatus.CLAIMED);
    }

    @Test
    void generatesTaskForReadyDramaBeforeAiSummaryExists() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        Drama drama = readyDrama("drama-1", "urban");
        drama.setAiSummary("");
        when(dramaRepository.findByStatusInAndCreatedAtGreaterThanEqual(
                any(),
                any(Instant.class),
                any(Sort.class)
        )).thenReturn(List.of(drama));
        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.existsByMediaAccountIdAndDramaId("media-1", "drama-1")).thenReturn(false);
        when(taskRepository.save(any(DistributionTask.class))).thenAnswer(invocation -> invocation.getArgument(0));

        List<DistributionTask> generated = service.generateTasksForOwner("owner-1");

        assertThat(generated).hasSize(1);
        assertThat(generated.getFirst().getDramaId()).isEqualTo("drama-1");
        verify(taskRepository).save(any(DistributionTask.class));
    }

    @Test
    void generatesTaskForBaiduDraftDramaToPrepareAssetsOnClaim() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        Drama baiduDraft = baiduDraftDrama("drama-baidu", "urban");
        Drama hongguoDraft = baiduDraftDrama("drama-hongguo", "urban");
        hongguoDraft.setSource(DramaSources.HONGGUO_52API);

        when(dramaRepository.findByStatusInAndCreatedAtGreaterThanEqual(
                any(),
                any(Instant.class),
                any(Sort.class)
        )).thenReturn(List.of(baiduDraft, hongguoDraft));
        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.existsByMediaAccountIdAndDramaId("media-1", "drama-baidu")).thenReturn(false);
        when(taskRepository.save(any(DistributionTask.class))).thenAnswer(invocation -> invocation.getArgument(0));

        List<DistributionTask> generated = service.generateTasksForOwner("owner-1");

        assertThat(generated).hasSize(1);
        assertThat(generated.getFirst().getDramaId()).isEqualTo("drama-baidu");
        assertThat(generated.getFirst().getStatus()).isEqualTo(DistributionTaskStatus.PENDING);
        verify(taskRepository).save(any(DistributionTask.class));
        verify(taskRepository, never()).existsByMediaAccountIdAndDramaId("media-1", "drama-hongguo");
    }

    @Test
    void claimMarksPreparedBaiduDraftDramaReadyWithoutRegeneratingAssets() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        BaiduDramaPreparationService preparationService = mock(BaiduDramaPreparationService.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository, preparationService);

        DistributionTask pending = new DistributionTask();
        pending.setId("task-1");
        pending.setMediaAccountId("media-1");
        pending.setDramaId("drama-baidu");
        pending.setStatus(DistributionTaskStatus.PENDING);
        Drama drama = baiduDraftDrama("drama-baidu", "urban");
        markPrepared(drama);

        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.findFirstByStatusAndMediaAccountIdInOrderByPriorityDescCreatedAtAsc(
                DistributionTaskStatus.PENDING,
                List.of("media-1")
        )).thenReturn(Optional.of(pending));
        when(dramaRepository.findById("drama-baidu")).thenReturn(Optional.of(drama));
        when(dramaRepository.save(drama)).thenReturn(drama);
        when(taskRepository.save(pending)).thenReturn(pending);

        Optional<DistributionTask> claimed = service.claimForOwner("owner-1", "device-1");

        assertThat(claimed).contains(pending);
        assertThat(drama.getStatus()).isEqualTo(DramaStatus.READY);
        assertThat(pending.getStatus()).isEqualTo(DistributionTaskStatus.CLAIMED);
        verify(preparationService, never()).prepareForDistribution(any());
        verify(dramaRepository).save(drama);
    }

    @Test
    void skipsDramaWhenBlockingTaskAlreadyExistsForSameMediaAccount() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        Drama drama = new Drama();
        drama.setId("drama-1");
        drama.setStatus(DramaStatus.READY);
        drama.setCategoryIds(List.of("urban"));
        DramaEpisode episode = new DramaEpisode();
        episode.setEpisodeNo(1);
        episode.setSourcePath("/drama/1.mp4");
        drama.setEpisodes(List.of(episode));
        markPrepared(drama);

        when(dramaRepository.findByStatusInAndCreatedAtGreaterThanEqual(
                any(),
                any(Instant.class),
                any(Sort.class)
        )).thenReturn(List.of(drama));
        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(activeMedia("media-2", "owner-1", "urban")));
        when(taskRepository.existsByMediaAccountIdAndDramaId("media-2", "drama-1")).thenReturn(true);

        assertThat(service.generateTasksForOwner("owner-1")).isEmpty();
        verify(taskRepository, never()).save(any(DistributionTask.class));
    }

    @Test
    void priorityTaskUsesFirstEligibleMediaWithoutDuplicateForSameMedia() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        Drama drama = new Drama();
        drama.setId("drama-1");
        drama.setStatus(DramaStatus.READY);
        drama.setCategoryIds(List.of("urban"));
        markCreatedNow(drama);
        DramaEpisode episode = new DramaEpisode();
        episode.setEpisodeNo(1);
        episode.setSourcePath("/drama/1.mp4");
        drama.setEpisodes(List.of(episode));
        markPrepared(drama);

        when(dramaRepository.findById("drama-1")).thenReturn(Optional.of(drama));
        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.findFirstByDramaIdAndStatusAndMediaAccountIdInOrderByCreatedAtAsc(
                "drama-1",
                DistributionTaskStatus.PENDING,
                List.of("media-1")
        )).thenReturn(Optional.empty());
        when(taskRepository.existsByMediaAccountIdAndDramaId("media-1", "drama-1")).thenReturn(false);
        when(taskRepository.save(any(DistributionTask.class))).thenAnswer(invocation -> invocation.getArgument(0));

        DistributionTask task = service.prioritizeDramaForOwner("owner-1", "drama-1");

        assertThat(task.getDramaId()).isEqualTo("drama-1");
        assertThat(task.getMediaAccountId()).isEqualTo("media-1");
        assertThat(task.getPriority()).isEqualTo(100);
        verify(taskRepository).existsByMediaAccountIdAndDramaId("media-1", "drama-1");
    }

    @Test
    void priorityRaisesExistingPendingTaskInsteadOfCreatingDuplicate() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        Drama drama = new Drama();
        drama.setId("drama-1");
        drama.setStatus(DramaStatus.READY);
        drama.setCategoryIds(List.of("urban"));
        markCreatedNow(drama);
        markPrepared(drama);
        DramaEpisode episode = new DramaEpisode();
        episode.setEpisodeNo(1);
        episode.setSourcePath("/drama/1.mp4");
        drama.setEpisodes(List.of(episode));
        DistributionTask existing = new DistributionTask();
        existing.setId("task-1");
        existing.setDramaId("drama-1");
        existing.setMediaAccountId("media-1");
        existing.setStatus(DistributionTaskStatus.PENDING);
        existing.setPriority(0);

        when(dramaRepository.findById("drama-1")).thenReturn(Optional.of(drama));
        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.findFirstByDramaIdAndStatusAndMediaAccountIdInOrderByCreatedAtAsc(
                "drama-1",
                DistributionTaskStatus.PENDING,
                List.of("media-1")
        )).thenReturn(Optional.of(existing));
        when(taskRepository.save(existing)).thenReturn(existing);

        DistributionTask task = service.prioritizeDramaForOwner("owner-1", "drama-1");

        assertThat(task.getId()).isEqualTo("task-1");
        assertThat(task.getPriority()).isEqualTo(100);
        verify(taskRepository, never()).existsActiveByDramaId("drama-1");
    }

    @Test
    void priorityRejectsDramaOutsideRecentCreatedPool() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        Drama drama = new Drama();
        drama.setId("drama-old");
        drama.setStatus(DramaStatus.READY);
        ReflectionTestUtils.setField(drama, "createdAt", Instant.now().minusSeconds(8 * 24 * 60 * 60));
        when(dramaRepository.findById("drama-old")).thenReturn(Optional.of(drama));

        assertThatThrownBy(() -> service.prioritizeDramaForOwner("owner-1", "drama-old"))
                .hasMessage("短剧不在近 7 天创建剧池内");
        verify(mediaAccountRepository, never()).findByOwnerAccountId("owner-1");
        verify(taskRepository, never()).save(any(DistributionTask.class));
    }

    @Test
    void cancelledDramaAlreadyInTaskListDoesNotGenerateDuplicate() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        Drama drama = new Drama();
        drama.setId("drama-1");
        drama.setStatus(DramaStatus.READY);
        drama.setCategoryIds(List.of("urban"));
        DramaEpisode episode = new DramaEpisode();
        episode.setEpisodeNo(1);
        episode.setSourcePath("/drama/1.mp4");
        drama.setEpisodes(List.of(episode));
        markPrepared(drama);

        when(dramaRepository.findByStatusInAndCreatedAtGreaterThanEqual(
                any(),
                any(Instant.class),
                any(Sort.class)
        )).thenReturn(List.of(drama));
        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.existsByMediaAccountIdAndDramaId("media-1", "drama-1")).thenReturn(true);

        assertThat(service.generateTasksForOwner("owner-1")).isEmpty();
        verify(taskRepository).existsByMediaAccountIdAndDramaId("media-1", "drama-1");
        verify(taskRepository, never()).save(any(DistributionTask.class));
    }

    @Test
    void forceStoppedDramaAlreadyInTaskListDoesNotGenerateDuplicate() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        Drama drama = readyDrama("drama-1", "urban");

        when(dramaRepository.findByStatusInAndCreatedAtGreaterThanEqual(
                any(),
                any(Instant.class),
                any(Sort.class)
        )).thenReturn(List.of(drama));
        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.existsByMediaAccountIdAndDramaId("media-1", "drama-1")).thenReturn(true);

        assertThat(service.generateTasksForOwner("owner-1")).isEmpty();
        verify(taskRepository, never()).save(any(DistributionTask.class));
    }

    @Test
    void aiPreparationFailureBlocksAutomaticRegenerationUntilManualRetry() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        Drama drama = readyDrama("drama-1", "urban");
        DistributionTask failed = new DistributionTask();
        failed.setMediaAccountId("media-1");
        failed.setDramaId("drama-1");
        failed.setStatus(DistributionTaskStatus.FAILED);
        failed.setFailureReason("AI 素材生成失败：OpenAI 配置无效");

        when(dramaRepository.findByStatusInAndCreatedAtGreaterThanEqual(
                any(),
                any(Instant.class),
                any(Sort.class)
        )).thenReturn(List.of(drama));
        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.existsByMediaAccountIdAndDramaId("media-1", "drama-1")).thenReturn(true);

        assertThat(service.generateTasksForOwner("owner-1")).isEmpty();
        verify(taskRepository, never()).save(any(DistributionTask.class));
    }

    @Test
    void generatesFromRecentCreatedReadyPoolOrderedByCreatedAtDesc() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);
        when(dramaRepository.findByStatusInAndCreatedAtGreaterThanEqual(
                any(),
                any(Instant.class),
                any(Sort.class)
        )).thenReturn(List.of());

        service.generateTasksForOwner("owner-1");

        verify(dramaRepository).findByStatusInAndCreatedAtGreaterThanEqual(
                any(),
                any(Instant.class),
                org.mockito.ArgumentMatchers.argThat(sort -> sort.toString().contains("createdAt: DESC"))
        );
        verify(dramaRepository, never()).findByStatus(DramaStatus.READY);
    }

    @Test
    void listsAdminTasksWithDisplayNamesAndPagination() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        AccountRepository accountRepository = mock(AccountRepository.class);
        DistributionService service = new DistributionService(
                dramaRepository,
                mediaAccountRepository,
                taskRepository,
                accountRepository,
                null
        );

        DistributionTask task = new DistributionTask();
        task.setId("task-1");
        task.setMediaAccountId("media-1");
        task.setDramaId("drama-1");
        task.setStatus(DistributionTaskStatus.PENDING);

        MediaAccount media = new MediaAccount();
        media.setId("media-1");
        media.setDisplayName("视频号主账号");
        media.setOwnerAccountId("owner-1");

        Account account = new Account();
        account.setId("owner-1");
        account.setUsername("owner-user");

        Drama drama = new Drama();
        drama.setId("drama-1");
        drama.setTitle("原始剧名");
        drama.setAiTitle("神医归来");

        PageRequest pageable = PageRequest.of(0, 10);
        when(taskRepository.findAll(pageable)).thenReturn(new PageImpl<>(List.of(task), pageable, 1));
        when(mediaAccountRepository.findAllById(List.of("media-1"))).thenReturn(List.of(media));
        when(accountRepository.findAllById(List.of("owner-1"))).thenReturn(List.of(account));
        when(dramaRepository.findAllById(List.of("drama-1"))).thenReturn(List.of(drama));

        PageResult<DistributionDtos.AdminTaskResponse> result = service.listAdminTasks(pageable);

        assertThat(result.totalElements()).isEqualTo(1);
        assertThat(result.content()).singleElement()
                .satisfies(item -> {
                    assertThat(item.ownerAccountId()).isEqualTo("owner-1");
                    assertThat(item.ownerUsername()).isEqualTo("owner-user");
                    assertThat(item.mediaAccountName()).isEqualTo("视频号主账号");
                    assertThat(item.dramaTitle()).isEqualTo("神医归来");
                });
    }

    @Test
    void fallbackAdminTaskSearchMatchesAiDramaTitle() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        DistributionTask task = new DistributionTask();
        task.setId("task-1");
        task.setMediaAccountId("media-1");
        task.setDramaId("drama-1");
        task.setStatus(DistributionTaskStatus.PENDING);

        MediaAccount media = new MediaAccount();
        media.setId("media-1");
        media.setDisplayName("视频号主账号");

        Drama drama = new Drama();
        drama.setId("drama-1");
        drama.setTitle("原始剧名");
        drama.setAiTitle("神医归来");

        when(taskRepository.findAll()).thenReturn(List.of(task));
        when(mediaAccountRepository.findAllById(eq(List.of("media-1")))).thenReturn(List.of(media));
        when(dramaRepository.findAllById(eq(List.of("drama-1")))).thenReturn(List.of(drama));

        PageResult<DistributionDtos.AdminTaskResponse> result = service.listAdminTasks(
                "神医归来",
                null,
                PageRequest.of(0, 10)
        );

        assertThat(result.content()).singleElement()
                .satisfies(item -> assertThat(item.dramaTitle()).isEqualTo("神医归来"));
    }

    @Test
    void adminTaskStatusCountsIncludesAllStatuses() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        DistributionTask pending = new DistributionTask();
        pending.setMediaAccountId("media-1");
        pending.setDramaId("drama-1");
        pending.setStatus(DistributionTaskStatus.PENDING);
        DistributionTask failed = new DistributionTask();
        failed.setMediaAccountId("media-1");
        failed.setDramaId("drama-1");
        failed.setStatus(DistributionTaskStatus.FAILED);

        when(taskRepository.findAll()).thenReturn(List.of(pending, failed));
        when(mediaAccountRepository.findAllById(List.of("media-1"))).thenReturn(List.of());
        when(dramaRepository.findAllById(List.of("drama-1"))).thenReturn(List.of());

        List<DistributionDtos.TaskStatusCount> counts = service.adminTaskStatusCounts(null);

        assertThat(counts).hasSize(DistributionTaskStatus.values().length);
        assertThat(counts)
                .filteredOn(item -> item.status() == DistributionTaskStatus.PENDING)
                .singleElement()
                .satisfies(item -> assertThat(item.count()).isEqualTo(1));
        assertThat(counts)
                .filteredOn(item -> item.status() == DistributionTaskStatus.FAILED)
                .singleElement()
                .satisfies(item -> assertThat(item.count()).isEqualTo(1));
        assertThat(counts)
                .filteredOn(item -> item.status() == DistributionTaskStatus.SUCCEEDED)
                .singleElement()
                .satisfies(item -> assertThat(item.count()).isZero());
    }

    @Test
    void desktopRetryClaimsFailedTaskForCurrentOwnerAndClearsFailureState() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        DistributionTask failed = new DistributionTask();
        failed.setId("task-1");
        failed.setMediaAccountId("media-1");
        failed.setDramaId("drama-1");
        failed.setStatus(DistributionTaskStatus.FAILED);
        failed.setProgress(75);
        failed.setFailureReason("upload failed");
        failed.setPlatformPublishId("old-publish");
        failed.setFinishedAt(Instant.now());

        when(mediaAccountRepository.findByOwnerAccountId("owner-1"))
                .thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.findById("task-1")).thenReturn(Optional.of(failed));
        when(taskRepository.save(failed)).thenReturn(failed);

        DistributionTask task = service.retryAndClaimForOwner("owner-1", "task-1", "device-1");

        assertThat(task.getStatus()).isEqualTo(DistributionTaskStatus.CLAIMED);
        assertThat(task.getLockedByDeviceId()).isEqualTo("device-1");
        assertThat(task.getProgress()).isZero();
        assertThat(task.getFailureReason()).isNull();
        assertThat(task.getPlatformPublishId()).isNull();
        assertThat(task.getFinishedAt()).isNull();
    }

    @Test
    void desktopRetryRejectsWhenDailyPublishLimitReached() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        DistributionTask failed = new DistributionTask();
        failed.setId("task-1");
        failed.setMediaAccountId("media-1");
        failed.setDramaId("drama-1");
        failed.setStatus(DistributionTaskStatus.FAILED);
        failed.setFailureReason("upload failed");
        failed.setFinishedAt(Instant.now());
        failed.setCreatedAt(Instant.now().minusSeconds(25 * 60 * 60));

        when(mediaAccountRepository.findByOwnerAccountId("owner-1"))
                .thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.findById("task-1")).thenReturn(Optional.of(failed));
        when(taskRepository.countByMediaAccountIdInAndUpdatedAtGreaterThanEqualAndStatusIn(
                eq(List.of("media-1")),
                any(Instant.class),
                any()
        )).thenReturn(10L);

        assertThatThrownBy(() -> service.retryAndClaimForOwner("owner-1", "task-1", "device-1"))
                .hasMessageContaining("今日发布次数已达 10 次");

        verify(taskRepository, never()).save(any(DistributionTask.class));
    }

    @Test
    void desktopRetryUsesSeparateDailyPublishLimitByPlatform() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        DistributionTask failed = new DistributionTask();
        failed.setId("task-1");
        failed.setMediaAccountId("media-tiktok");
        failed.setPlatform(MediaPlatform.TIKTOK);
        failed.setDramaId("drama-1");
        failed.setStatus(DistributionTaskStatus.FAILED);
        failed.setFailureReason("upload failed");
        failed.setFinishedAt(Instant.now());
        failed.setCreatedAt(Instant.now().minusSeconds(25 * 60 * 60));

        MediaAccount wechat = activeMedia("media-wechat", "owner-1", "urban", MediaPlatform.WECHAT_VIDEO);
        MediaAccount tiktok = activeMedia("media-tiktok", "owner-1", "urban", MediaPlatform.TIKTOK);

        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(wechat, tiktok));
        when(taskRepository.findById("task-1")).thenReturn(Optional.of(failed));
        when(taskRepository.countByMediaAccountIdInAndUpdatedAtGreaterThanEqualAndStatusIn(
                eq(List.of("media-tiktok")),
                any(Instant.class),
                any()
        )).thenReturn(0L);
        when(taskRepository.save(failed)).thenReturn(failed);

        DistributionTask task = service.retryAndClaimForOwner("owner-1", "task-1", "device-1");

        assertThat(task.getMediaAccountId()).isEqualTo("media-tiktok");
        assertThat(task.getPlatform()).isEqualTo(MediaPlatform.TIKTOK);
        assertThat(task.getStatus()).isEqualTo(DistributionTaskStatus.CLAIMED);
        verify(taskRepository, never()).countByMediaAccountIdInAndUpdatedAtGreaterThanEqualAndStatusIn(
                eq(List.of("media-wechat")),
                any(Instant.class),
                any()
        );
    }

    @Test
    void desktopRetryBypassesDailyPublishLimitForTasksCreatedWithin24Hours() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        DistributionTask failed = new DistributionTask();
        failed.setId("task-1");
        failed.setMediaAccountId("media-1");
        failed.setDramaId("drama-1");
        failed.setStatus(DistributionTaskStatus.FAILED);
        failed.setFailureReason("upload failed");
        failed.setFinishedAt(Instant.now());
        failed.setCreatedAt(Instant.now().minusSeconds(23 * 60 * 60));

        when(mediaAccountRepository.findByOwnerAccountId("owner-1"))
                .thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.findById("task-1")).thenReturn(Optional.of(failed));
        when(taskRepository.save(failed)).thenReturn(failed);

        DistributionTask task = service.retryAndClaimForOwner("owner-1", "task-1", "device-1");

        assertThat(task.getStatus()).isEqualTo(DistributionTaskStatus.CLAIMED);
        assertThat(task.getLockedByDeviceId()).isEqualTo("device-1");
        assertThat(task.getFailureReason()).isNull();
        verify(taskRepository, never()).countByMediaAccountIdInAndUpdatedAtGreaterThanEqualAndStatusIn(any(), any(), any());
    }

    @Test
    void desktopRetryClaimsStuckDownloadingTaskForCurrentOwner() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        DistributionTask downloading = new DistributionTask();
        downloading.setId("task-1");
        downloading.setMediaAccountId("media-1");
        downloading.setDramaId("drama-1");
        downloading.setStatus(DistributionTaskStatus.DOWNLOADING);
        downloading.setProgress(10);
        downloading.setLockedByDeviceId("old-device");

        when(mediaAccountRepository.findByOwnerAccountId("owner-1"))
                .thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.findById("task-1")).thenReturn(Optional.of(downloading));
        when(taskRepository.save(downloading)).thenReturn(downloading);

        DistributionTask task = service.retryAndClaimForOwner("owner-1", "task-1", "device-1");

        assertThat(task.getStatus()).isEqualTo(DistributionTaskStatus.CLAIMED);
        assertThat(task.getLockedByDeviceId()).isEqualTo("device-1");
        assertThat(task.getProgress()).isZero();
    }

    @Test
    void desktopRetryRejectsRecentlyUpdatedActiveTask() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        DistributionTask downloading = new DistributionTask();
        downloading.setId("task-1");
        downloading.setMediaAccountId("media-1");
        downloading.setDramaId("drama-1");
        downloading.setStatus(DistributionTaskStatus.DOWNLOADING);
        downloading.setProgress(30);
        downloading.setLockedByDeviceId("device-1");
        downloading.setUpdatedAt(Instant.now());

        when(mediaAccountRepository.findByOwnerAccountId("owner-1"))
                .thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.findById("task-1")).thenReturn(Optional.of(downloading));

        assertThatThrownBy(() -> service.retryAndClaimForOwner("owner-1", "task-1", "device-1"))
                .hasMessageContaining("任务仍在执行中");

        verify(taskRepository, never()).save(any(DistributionTask.class));
    }

    @Test
    void desktopRetryClaimsTimedOutActiveTask() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        DistributionTask downloading = new DistributionTask();
        downloading.setId("task-1");
        downloading.setMediaAccountId("media-1");
        downloading.setDramaId("drama-1");
        downloading.setStatus(DistributionTaskStatus.DOWNLOADING);
        downloading.setProgress(30);
        downloading.setLockedByDeviceId("old-device");
        downloading.setUpdatedAt(Instant.now().minusSeconds(16 * 60));

        when(mediaAccountRepository.findByOwnerAccountId("owner-1"))
                .thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.findById("task-1")).thenReturn(Optional.of(downloading));
        when(taskRepository.save(downloading)).thenReturn(downloading);

        DistributionTask task = service.retryAndClaimForOwner("owner-1", "task-1", "device-1");

        assertThat(task.getStatus()).isEqualTo(DistributionTaskStatus.CLAIMED);
        assertThat(task.getLockedByDeviceId()).isEqualTo("device-1");
        assertThat(task.getProgress()).isZero();
    }

    @Test
    void adminRetryRejectsRecentlyUpdatedActiveTask() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        DistributionTask uploading = new DistributionTask();
        uploading.setId("task-1");
        uploading.setMediaAccountId("media-1");
        uploading.setDramaId("drama-1");
        uploading.setStatus(DistributionTaskStatus.UPLOADING);
        uploading.setProgress(75);
        uploading.setLockedByDeviceId("device-1");
        uploading.setUpdatedAt(Instant.now());

        when(taskRepository.findById("task-1")).thenReturn(Optional.of(uploading));

        assertThatThrownBy(() -> service.retryTaskFromAdmin("task-1"))
                .hasMessageContaining("任务仍在执行中");

        verify(taskRepository, never()).save(any(DistributionTask.class));
    }

    @Test
    void desktopReleaseTaskReturnsItToPendingPoolForCurrentOwner() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        DistributionTask task = new DistributionTask();
        task.setId("task-1");
        task.setMediaAccountId("media-1");
        task.setDramaId("drama-1");
        task.setStatus(DistributionTaskStatus.DOWNLOADING);
        task.setProgress(40);
        task.setLockedByDeviceId("device-1");
        task.setFailureReason("old error");
        task.setPlatformPublishId("old-publish");
        task.setFinishedAt(Instant.now());

        when(mediaAccountRepository.findByOwnerAccountId("owner-1"))
                .thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.findById("task-1")).thenReturn(Optional.of(task));
        when(taskRepository.save(task)).thenReturn(task);

        DistributionTask released = service.releaseTaskForOwner("owner-1", "task-1");

        assertThat(released.getStatus()).isEqualTo(DistributionTaskStatus.PENDING);
        assertThat(released.getProgress()).isZero();
        assertThat(released.getLockedByDeviceId()).isNull();
        assertThat(released.getFailureReason()).isNull();
        assertThat(released.getPlatformPublishId()).isNull();
        assertThat(released.getFinishedAt()).isNull();
    }

    @Test
    void desktopForceStopCancelsRunningTaskForCurrentOwner() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        DistributionTask task = new DistributionTask();
        task.setId("task-1");
        task.setMediaAccountId("media-1");
        task.setDramaId("drama-1");
        task.setStatus(DistributionTaskStatus.UPLOADING);
        task.setProgress(75);
        task.setLockedByDeviceId("device-1");

        when(mediaAccountRepository.findByOwnerAccountId("owner-1"))
                .thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.findById("task-1")).thenReturn(Optional.of(task));
        when(taskRepository.save(task)).thenReturn(task);

        DistributionTask stopped = service.forceStopTaskForOwner("owner-1", "task-1");

        assertThat(stopped.getStatus()).isEqualTo(DistributionTaskStatus.CANCELLED);
        assertThat(stopped.getProgress()).isEqualTo(75);
        assertThat(stopped.getLockedByDeviceId()).isNull();
        assertThat(stopped.getFailureReason()).isEqualTo("用户强制停止任务");
        assertThat(stopped.getFinishedAt()).isNotNull();
        verify(taskRepository).save(task);
    }

    @Test
    void desktopForceStopCancelsPendingTaskForCurrentOwner() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        DistributionTask task = new DistributionTask();
        task.setId("task-1");
        task.setMediaAccountId("media-1");
        task.setDramaId("drama-1");
        task.setStatus(DistributionTaskStatus.PENDING);

        when(mediaAccountRepository.findByOwnerAccountId("owner-1"))
                .thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.findById("task-1")).thenReturn(Optional.of(task));
        when(taskRepository.save(task)).thenReturn(task);

        DistributionTask stopped = service.forceStopTaskForOwner("owner-1", "task-1");

        assertThat(stopped.getStatus()).isEqualTo(DistributionTaskStatus.CANCELLED);
        assertThat(stopped.getLockedByDeviceId()).isNull();
        assertThat(stopped.getFailureReason()).isEqualTo("用户强制停止任务");
        assertThat(stopped.getFinishedAt()).isNotNull();
        verify(taskRepository).save(task);
    }


    @Test
    void desktopForceStopRejectsTaskOutsideCurrentOwner() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        DistributionTask task = new DistributionTask();
        task.setId("task-1");
        task.setMediaAccountId("media-2");
        task.setStatus(DistributionTaskStatus.DOWNLOADING);

        when(mediaAccountRepository.findByOwnerAccountId("owner-1"))
                .thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.findById("task-1")).thenReturn(Optional.of(task));

        assertThatThrownBy(() -> service.forceStopTaskForOwner("owner-1", "task-1"))
                .hasMessageContaining("任务不存在");

        verify(taskRepository, never()).save(any(DistributionTask.class));
    }

    @Test
    void desktopForceStopRejectsFinishedTask() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        DistributionTask task = new DistributionTask();
        task.setId("task-1");
        task.setMediaAccountId("media-1");
        task.setStatus(DistributionTaskStatus.SUCCEEDED);

        when(mediaAccountRepository.findByOwnerAccountId("owner-1"))
                .thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.findById("task-1")).thenReturn(Optional.of(task));

        assertThatThrownBy(() -> service.forceStopTaskForOwner("owner-1", "task-1"))
                .hasMessageContaining("只有待执行或执行中的任务可以强制停止");

        verify(taskRepository, never()).save(any(DistributionTask.class));
    }

    @Test
    void desktopForceStopReturnsAlreadyCancelledTask() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        DistributionTask task = new DistributionTask();
        task.setId("task-1");
        task.setMediaAccountId("media-1");
        task.setStatus(DistributionTaskStatus.CANCELLED);

        when(mediaAccountRepository.findByOwnerAccountId("owner-1"))
                .thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.findById("task-1")).thenReturn(Optional.of(task));

        DistributionTask stopped = service.forceStopTaskForOwner("owner-1", "task-1");

        assertThat(stopped).isSameAs(task);
        verify(taskRepository, never()).save(any(DistributionTask.class));
    }

    private static MediaAccount activeMedia(String id, String ownerAccountId, String categoryId) {
        return activeMedia(id, ownerAccountId, categoryId, MediaPlatform.WECHAT_VIDEO);
    }

    private static MediaAccount activeMedia(String id, String ownerAccountId, String categoryId, MediaPlatform platform) {
        MediaAccount media = new MediaAccount();
        media.setId(id);
        media.setOwnerAccountId(ownerAccountId);
        media.setPlatform(platform);
        media.setStatus(MediaAccountStatus.ACTIVE);
        media.setLoginStateRef("profile");
        DistributionPolicy policy = new DistributionPolicy();
        policy.setEnabled(true);
        policy.setCategoryIds(List.of(categoryId));
        media.setDistributionPolicy(policy);
        return media;
    }

    private static Drama readyDrama(String id, String categoryId) {
        Drama drama = new Drama();
        drama.setId(id);
        drama.setStatus(DramaStatus.READY);
        drama.setCategoryIds(List.of(categoryId));
        markCreatedNow(drama);
        markPrepared(drama);
        DramaEpisode episode = new DramaEpisode();
        episode.setEpisodeNo(1);
        episode.setSourcePath("/drama/" + id + ".mp4");
        drama.setEpisodes(List.of(episode));
        return drama;
    }

    private static Drama baiduDraftDrama(String id, String categoryId) {
        Drama drama = new Drama();
        drama.setId(id);
        drama.setStatus(DramaStatus.DRAFT);
        drama.setSource(DramaSources.BAIDU_PAN);
        drama.setSourcePath("/drama/2026/7月14日/" + id);
        drama.setCategoryIds(List.of(categoryId));
        markCreatedNow(drama);
        DramaEpisode episode = new DramaEpisode();
        episode.setEpisodeNo(1);
        episode.setSourcePath("/drama/" + id + ".mp4");
        drama.setEpisodes(List.of(episode));
        return drama;
    }

    private static void markPrepared(Drama drama) {
        drama.setAiTitle("AI剧名");
        drama.setAiSummary("AI简介...");
        drama.setAiCoverUrl("/uploads/ai-covers/" + drama.getId() + ".jpg");
        drama.setAiVideoCoverUrl("/uploads/ai-covers/" + drama.getId() + "-video.jpg");
    }

    private static void markTiktokPrepared(Drama drama) {
        drama.setAiTitleEn("English Title");
        drama.setAiSummaryEn("English summary.");
        drama.setAiCoverEnUrl("/uploads/ai-covers/" + drama.getId() + "-en.jpg");
        drama.setAiVideoCoverEnUrl("/uploads/ai-covers/" + drama.getId() + "-en-video.jpg");
    }

    private static void markCreatedNow(Drama drama) {
        ReflectionTestUtils.setField(drama, "createdAt", Instant.now());
    }
}
