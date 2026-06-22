package com.onehot.aidrama.distribution;

import com.onehot.aidrama.dramas.Drama;
import com.onehot.aidrama.dramas.DramaEpisode;
import com.onehot.aidrama.dramas.DramaRepository;
import com.onehot.aidrama.dramas.DramaStatus;
import com.onehot.aidrama.media.DistributionPolicy;
import com.onehot.aidrama.media.MediaAccount;
import com.onehot.aidrama.media.MediaAccountRepository;
import com.onehot.aidrama.media.MediaAccountStatus;
import com.onehot.aidrama.common.PageResult;
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
        verify(dramaRepository, never()).findByStatusAndUpdatedAtGreaterThanEqual(
                any(DramaStatus.class),
                any(Instant.class),
                any(Sort.class)
        );
        verify(dramaRepository, never()).findByStatus(DramaStatus.READY);
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

        MediaAccount first = activeMedia("media-1", "owner-1", "urban");
        MediaAccount second = activeMedia("media-2", "owner-1", "urban");

        when(dramaRepository.findByStatusAndUpdatedAtGreaterThanEqual(
                any(DramaStatus.class),
                any(Instant.class),
                any(Sort.class)
        )).thenReturn(List.of(drama));
        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(first, second));
        when(taskRepository.existsByMediaAccountIdAndDramaId("media-1", "drama-1")).thenReturn(false);
        when(taskRepository.existsByMediaAccountIdAndDramaId("media-2", "drama-1")).thenReturn(false);
        when(taskRepository.save(any(DistributionTask.class))).thenAnswer(invocation -> invocation.getArgument(0));

        List<DistributionTask> generated = service.generateTasksForOwner("owner-1");

        assertThat(generated).hasSize(2);
        assertThat(generated).extracting(DistributionTask::getDramaId).containsOnly("drama-1");
        assertThat(generated).extracting(DistributionTask::getMediaAccountId).containsExactly("media-1", "media-2");
        verify(taskRepository, times(2)).save(any(DistributionTask.class));
    }

    @Test
    void skipsDramaWhenTaskAlreadyExistsForSameMediaAccount() {
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

        when(dramaRepository.findByStatusAndUpdatedAtGreaterThanEqual(
                any(DramaStatus.class),
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
        markUpdatedNow(drama);
        DramaEpisode episode = new DramaEpisode();
        episode.setEpisodeNo(1);
        episode.setSourcePath("/drama/1.mp4");
        drama.setEpisodes(List.of(episode));

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

        when(dramaRepository.findByStatusAndUpdatedAtGreaterThanEqual(
                any(DramaStatus.class),
                any(Instant.class),
                any(Sort.class)
        )).thenReturn(List.of(drama));
        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.existsByMediaAccountIdAndDramaId("media-1", "drama-1")).thenReturn(false);
        when(taskRepository.save(any(DistributionTask.class))).thenAnswer(invocation -> invocation.getArgument(0));

        assertThat(service.generateTasksForOwner("owner-1")).hasSize(1);
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

        PageRequest pageable = PageRequest.of(0, 10);
        when(taskRepository.findAll(pageable)).thenReturn(new PageImpl<>(List.of(task), pageable, 1));
        when(mediaAccountRepository.findAllById(List.of("media-1"))).thenReturn(List.of(media));
        when(dramaRepository.findAllById(List.of("drama-1"))).thenReturn(List.of(drama));

        PageResult<DistributionDtos.AdminTaskResponse> result = service.listAdminTasks(pageable);

        assertThat(result.totalElements()).isEqualTo(1);
        assertThat(result.content()).singleElement()
                .satisfies(item -> {
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
        DramaEpisode episode = new DramaEpisode();
        episode.setEpisodeNo(1);
        episode.setSourcePath("/drama/" + id + ".mp4");
        drama.setEpisodes(List.of(episode));
        return drama;
    }

    private static void markUpdatedNow(Drama drama) {
        ReflectionTestUtils.setField(drama, "updatedAt", Instant.now());
    }
}
