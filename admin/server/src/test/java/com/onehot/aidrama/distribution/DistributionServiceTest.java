package com.onehot.aidrama.distribution;

import com.onehot.aidrama.baiduyun.BaiduDramaPreparationService;
import com.onehot.aidrama.dramas.Drama;
import com.onehot.aidrama.dramas.DramaEpisode;
import com.onehot.aidrama.dramas.DramaRepository;
import com.onehot.aidrama.dramas.DramaStatus;
import com.onehot.aidrama.media.DistributionPolicy;
import com.onehot.aidrama.media.MediaAccount;
import com.onehot.aidrama.media.MediaAccountRepository;
import com.onehot.aidrama.media.MediaAccountStatus;
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
    private static final List<DistributionTaskStatus> NON_BLOCKING_GENERATION_STATUSES = List.of(
            DistributionTaskStatus.FAILED,
            DistributionTaskStatus.CANCELLED
    );

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
        verify(dramaRepository, never()).findByStatusAndUpdatedAtGreaterThanEqual(
                any(DramaStatus.class),
                any(Instant.class),
                any(Sort.class)
        );
        verify(dramaRepository, never()).findByStatus(DramaStatus.READY);
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
        when(dramaRepository.findByStatusAndUpdatedAtGreaterThanEqual(
                any(DramaStatus.class),
                any(Instant.class),
                any(Sort.class)
        )).thenReturn(List.of(firstDrama, secondDrama));
        when(taskRepository.existsByMediaAccountIdAndDramaIdAndStatusNotIn(
                "media-1",
                "drama-1",
                NON_BLOCKING_GENERATION_STATUSES
        )).thenReturn(false);
        when(taskRepository.save(any(DistributionTask.class))).thenAnswer(invocation -> invocation.getArgument(0));

        Optional<DistributionTask> claimed = service.prepareAndClaimForOwner("owner-1", "device-1");

        assertThat(claimed).isPresent();
        assertThat(claimed.get().getDramaId()).isEqualTo("drama-1");
        assertThat(claimed.get().getMediaAccountId()).isEqualTo("media-1");
        assertThat(claimed.get().getStatus()).isEqualTo(DistributionTaskStatus.CLAIMED);
        assertThat(claimed.get().getLockedByDeviceId()).isEqualTo("device-1");
        verify(taskRepository, times(2)).save(any(DistributionTask.class));
        verify(taskRepository, never()).existsByMediaAccountIdAndDramaIdAndStatusNotIn(
                "media-2",
                "drama-1",
                NON_BLOCKING_GENERATION_STATUSES
        );
        verify(taskRepository, never()).existsByMediaAccountIdAndDramaIdAndStatusNotIn(
                "media-1",
                "drama-2",
                NON_BLOCKING_GENERATION_STATUSES
        );
    }

    @Test
    void generatesOneTaskForEachEligibleMediaAccount() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        Drama drama = new Drama();
        drama.setId("drama-1");
        drama.setStatus(DramaStatus.READY);
        drama.setCategoryIds(List.of("urban"));
        markUpdatedNow(drama);
        DramaEpisode episode = new DramaEpisode();
        episode.setEpisodeNo(1);
        episode.setSourcePath("/drama/1.mp4");
        drama.setEpisodes(List.of(episode));
        markPrepared(drama);

        MediaAccount first = activeMedia("media-1", "owner-1", "urban");
        MediaAccount second = activeMedia("media-2", "owner-1", "urban");

        when(dramaRepository.findByStatusAndUpdatedAtGreaterThanEqual(
                any(DramaStatus.class),
                any(Instant.class),
                any(Sort.class)
        )).thenReturn(List.of(drama));
        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(first, second));
        when(taskRepository.existsByMediaAccountIdAndDramaIdAndStatusNotIn(
                "media-1",
                "drama-1",
                NON_BLOCKING_GENERATION_STATUSES
        )).thenReturn(false);
        when(taskRepository.existsByMediaAccountIdAndDramaIdAndStatusNotIn(
                "media-2",
                "drama-1",
                NON_BLOCKING_GENERATION_STATUSES
        )).thenReturn(false);
        when(taskRepository.save(any(DistributionTask.class))).thenAnswer(invocation -> invocation.getArgument(0));

        List<DistributionTask> generated = service.generateTasksForOwner("owner-1");

        assertThat(generated).hasSize(2);
        assertThat(generated).extracting(DistributionTask::getDramaId).containsOnly("drama-1");
        assertThat(generated).extracting(DistributionTask::getMediaAccountId).containsExactly("media-1", "media-2");
        verify(taskRepository, times(2)).save(any(DistributionTask.class));
    }

    @Test
    void generatesTaskForReadyDramaBeforeAiSummaryExists() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        Drama drama = readyDrama("drama-1", "urban");
        drama.setAiSummary("");
        when(dramaRepository.findByStatusAndUpdatedAtGreaterThanEqual(
                any(DramaStatus.class),
                any(Instant.class),
                any(Sort.class)
        )).thenReturn(List.of(drama));
        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.existsByMediaAccountIdAndDramaIdAndStatusNotIn(
                "media-1",
                "drama-1",
                NON_BLOCKING_GENERATION_STATUSES
        )).thenReturn(false);
        when(taskRepository.save(any(DistributionTask.class))).thenAnswer(invocation -> invocation.getArgument(0));

        List<DistributionTask> generated = service.generateTasksForOwner("owner-1");

        assertThat(generated).hasSize(1);
        assertThat(generated.getFirst().getDramaId()).isEqualTo("drama-1");
        verify(taskRepository).save(any(DistributionTask.class));
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

        when(dramaRepository.findByStatusAndUpdatedAtGreaterThanEqual(
                any(DramaStatus.class),
                any(Instant.class),
                any(Sort.class)
        )).thenReturn(List.of(drama));
        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(activeMedia("media-2", "owner-1", "urban")));
        when(taskRepository.existsByMediaAccountIdAndDramaIdAndStatusNotIn(
                "media-2",
                "drama-1",
                NON_BLOCKING_GENERATION_STATUSES
        )).thenReturn(true);

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
        markUpdatedNow(drama);
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
        when(taskRepository.existsByMediaAccountIdAndDramaIdAndStatusNotIn(
                "media-1",
                "drama-1",
                NON_BLOCKING_GENERATION_STATUSES
        )).thenReturn(false);
        when(taskRepository.save(any(DistributionTask.class))).thenAnswer(invocation -> invocation.getArgument(0));

        DistributionTask task = service.prioritizeDramaForOwner("owner-1", "drama-1");

        assertThat(task.getDramaId()).isEqualTo("drama-1");
        assertThat(task.getMediaAccountId()).isEqualTo("media-1");
        assertThat(task.getPriority()).isEqualTo(100);
        verify(taskRepository).existsByMediaAccountIdAndDramaIdAndStatusNotIn(
                "media-1",
                "drama-1",
                NON_BLOCKING_GENERATION_STATUSES
        );
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
        markUpdatedNow(drama);
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
    void priorityRejectsDramaOutsideRecentUpdatedPool() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);

        Drama drama = new Drama();
        drama.setId("drama-old");
        drama.setStatus(DramaStatus.READY);
        ReflectionTestUtils.setField(drama, "updatedAt", Instant.now().minusSeconds(8 * 24 * 60 * 60));
        when(dramaRepository.findById("drama-old")).thenReturn(Optional.of(drama));

        assertThatThrownBy(() -> service.prioritizeDramaForOwner("owner-1", "drama-old"))
                .hasMessage("短剧不在最近更新剧池内");
        verify(mediaAccountRepository, never()).findByOwnerAccountId("owner-1");
        verify(taskRepository, never()).save(any(DistributionTask.class));
    }

    @Test
    void cancelledDramaCanBeGeneratedAgain() {
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

        when(dramaRepository.findByStatusAndUpdatedAtGreaterThanEqual(
                any(DramaStatus.class),
                any(Instant.class),
                any(Sort.class)
        )).thenReturn(List.of(drama));
        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.existsByMediaAccountIdAndDramaIdAndStatusNotIn(
                "media-1",
                "drama-1",
                NON_BLOCKING_GENERATION_STATUSES
        )).thenReturn(false);
        when(taskRepository.save(any(DistributionTask.class))).thenAnswer(invocation -> invocation.getArgument(0));

        assertThat(service.generateTasksForOwner("owner-1")).hasSize(1);
        verify(taskRepository).existsByMediaAccountIdAndDramaIdAndStatusNotIn(
                "media-1",
                "drama-1",
                NON_BLOCKING_GENERATION_STATUSES
        );
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

        when(dramaRepository.findByStatusAndUpdatedAtGreaterThanEqual(
                any(DramaStatus.class),
                any(Instant.class),
                any(Sort.class)
        )).thenReturn(List.of(drama));
        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.existsByMediaAccountIdAndDramaIdAndStatusNotIn(
                "media-1",
                "drama-1",
                NON_BLOCKING_GENERATION_STATUSES
        )).thenReturn(false);
        when(taskRepository.findFirstByMediaAccountIdAndDramaIdAndStatusOrderByCreatedAtDesc(
                "media-1",
                "drama-1",
                DistributionTaskStatus.FAILED
        )).thenReturn(Optional.of(failed));

        assertThat(service.generateTasksForOwner("owner-1")).isEmpty();
        verify(taskRepository, never()).save(any(DistributionTask.class));
    }

    @Test
    void generatesFromSameRecentUpdatedReadyPoolAsDesktopDramaList() {
        DramaRepository dramaRepository = mock(DramaRepository.class);
        MediaAccountRepository mediaAccountRepository = mock(MediaAccountRepository.class);
        DistributionTaskRepository taskRepository = mock(DistributionTaskRepository.class);
        DistributionService service = new DistributionService(dramaRepository, mediaAccountRepository, taskRepository);
        when(dramaRepository.findByStatusAndUpdatedAtGreaterThanEqual(
                any(DramaStatus.class),
                any(Instant.class),
                any(Sort.class)
        )).thenReturn(List.of());

        service.generateTasksForOwner("owner-1");

        verify(dramaRepository).findByStatusAndUpdatedAtGreaterThanEqual(
                any(DramaStatus.class),
                any(Instant.class),
                org.mockito.ArgumentMatchers.argThat(sort -> sort.toString().contains("updatedAt: DESC"))
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
        MediaAccount media = new MediaAccount();
        media.setId(id);
        media.setOwnerAccountId(ownerAccountId);
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
        markUpdatedNow(drama);
        markPrepared(drama);
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

    private static void markUpdatedNow(Drama drama) {
        ReflectionTestUtils.setField(drama, "updatedAt", Instant.now());
    }
}
