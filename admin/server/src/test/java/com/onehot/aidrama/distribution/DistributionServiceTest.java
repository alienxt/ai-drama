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

import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class DistributionServiceTest {
    @Test
    void preparesAndClaimsTaskForCurrentOwnerOnly() {
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

        MediaAccount owned = new MediaAccount();
        owned.setId("media-owned");
        owned.setOwnerAccountId("owner-1");
        owned.setStatus(MediaAccountStatus.ACTIVE);
        DistributionPolicy policy = new DistributionPolicy();
        policy.setEnabled(true);
        policy.setCategoryIds(List.of("urban"));
        owned.setDistributionPolicy(policy);

        when(dramaRepository.findByStatus(DramaStatus.READY)).thenReturn(List.of(drama));
        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(owned));
        when(taskRepository.existsActiveByDramaId("drama-1")).thenReturn(false);
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
    }

    @Test
    void generatesOnlyOneTaskPerDramaAcrossMultipleMediaAccounts() {
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

        MediaAccount first = activeMedia("media-1", "owner-1", "urban");
        MediaAccount second = activeMedia("media-2", "owner-1", "urban");

        when(dramaRepository.findByStatus(DramaStatus.READY)).thenReturn(List.of(drama));
        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(first, second));
        when(taskRepository.existsActiveByDramaId("drama-1")).thenReturn(false);
        when(taskRepository.save(any(DistributionTask.class))).thenAnswer(invocation -> invocation.getArgument(0));

        List<DistributionTask> generated = service.generateTasksForOwner("owner-1");

        assertThat(generated).hasSize(1);
        assertThat(generated.getFirst().getDramaId()).isEqualTo("drama-1");
        verify(taskRepository).save(any(DistributionTask.class));
    }

    @Test
    void skipsDramaWhenAnyTaskAlreadyExistsForThatDrama() {
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

        when(dramaRepository.findByStatus(DramaStatus.READY)).thenReturn(List.of(drama));
        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(activeMedia("media-2", "owner-1", "urban")));
        when(taskRepository.existsActiveByDramaId("drama-1")).thenReturn(true);

        assertThat(service.generateTasksForOwner("owner-1")).isEmpty();
        verify(taskRepository, never()).save(any(DistributionTask.class));
    }

    @Test
    void priorityTaskUsesFirstEligibleMediaAndDoesNotDuplicateActiveDrama() {
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

        when(dramaRepository.findById("drama-1")).thenReturn(Optional.of(drama));
        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.findFirstByDramaIdAndStatusAndMediaAccountIdInOrderByCreatedAtAsc(
                "drama-1",
                DistributionTaskStatus.PENDING,
                List.of("media-1")
        )).thenReturn(Optional.empty());
        when(taskRepository.existsActiveByDramaId("drama-1")).thenReturn(false);
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

        when(dramaRepository.findByStatus(DramaStatus.READY)).thenReturn(List.of(drama));
        when(mediaAccountRepository.findByOwnerAccountId("owner-1")).thenReturn(List.of(activeMedia("media-1", "owner-1", "urban")));
        when(taskRepository.existsActiveByDramaId("drama-1")).thenReturn(false);
        when(taskRepository.save(any(DistributionTask.class))).thenAnswer(invocation -> invocation.getArgument(0));

        assertThat(service.generateTasksForOwner("owner-1")).hasSize(1);
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
        drama.setTitle("神医归来");

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
}
