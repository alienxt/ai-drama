package com.onehot.aidrama.distribution;

import com.onehot.aidrama.common.PageResult;
import com.onehot.aidrama.common.error.BusinessException;
import com.onehot.aidrama.dramas.DramaRepository;
import com.onehot.aidrama.dramas.DramaStatus;
import com.onehot.aidrama.media.MediaAccount;
import com.onehot.aidrama.media.MediaAccountRepository;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.PageImpl;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
public class DistributionService {
    private final DramaRepository dramaRepository;
    private final MediaAccountRepository mediaAccountRepository;
    private final DistributionTaskRepository taskRepository;
    private final DistributionPlanner planner = new DistributionPlanner();

    public DistributionService(
            DramaRepository dramaRepository,
            MediaAccountRepository mediaAccountRepository,
            DistributionTaskRepository taskRepository
    ) {
        this.dramaRepository = dramaRepository;
        this.mediaAccountRepository = mediaAccountRepository;
        this.taskRepository = taskRepository;
    }

    public List<DistributionTask> generateTasks() {
        var dramas = dramaRepository.findByStatus(DramaStatus.READY);
        var mediaAccounts = mediaAccountRepository.findAll();
        return generateTasksForMediaAccounts(mediaAccounts, dramas);
    }

    public PageResult<DistributionDtos.AdminTaskResponse> listAdminTasks(Pageable pageable) {
        return listAdminTasks(null, null, pageable);
    }

    public PageResult<DistributionDtos.AdminTaskResponse> listAdminTasks(String keyword, DistributionTaskStatus status, Pageable pageable) {
        var taskPage = taskRepository.findAll(pageable);
        List<String> mediaAccountIds = taskPage.getContent().stream()
                .map(DistributionTask::getMediaAccountId)
                .distinct()
                .toList();
        List<String> dramaIds = taskPage.getContent().stream()
                .map(DistributionTask::getDramaId)
                .distinct()
                .toList();
        Map<String, MediaAccount> mediaById = mediaAccountRepository.findAllById(mediaAccountIds).stream()
                .collect(Collectors.toMap(MediaAccount::getId, Function.identity()));
        Map<String, com.onehot.aidrama.dramas.Drama> dramaById = dramaRepository.findAllById(dramaIds).stream()
                .collect(Collectors.toMap(com.onehot.aidrama.dramas.Drama::getId, Function.identity()));
        var rows = taskPage.getContent().stream().map(task -> DistributionDtos.AdminTaskResponse.from(
                task,
                Optional.ofNullable(mediaById.get(task.getMediaAccountId())).map(MediaAccount::getDisplayName).orElse(task.getMediaAccountId()),
                Optional.ofNullable(dramaById.get(task.getDramaId())).map(com.onehot.aidrama.dramas.Drama::getTitle).orElse(task.getDramaId())
        )).filter(row -> status == null || row.status() == status)
                .filter(row -> keyword == null || keyword.isBlank() || contains(row.id(), keyword)
                        || contains(row.mediaAccountName(), keyword) || contains(row.dramaTitle(), keyword))
                .toList();
        return PageResult.from(new PageImpl<>(rows, pageable, rows.size()));
    }

    private boolean contains(String value, String keyword) {
        return value != null && value.toLowerCase().contains(keyword.trim().toLowerCase());
    }

    public List<DistributionTask> generateTasksForOwner(String ownerAccountId) {
        var dramas = dramaRepository.findByStatus(DramaStatus.READY);
        var mediaAccounts = mediaAccountRepository.findByOwnerAccountId(ownerAccountId);
        return generateTasksForMediaAccounts(mediaAccounts, dramas);
    }

    public Optional<DistributionTask> claimForOwner(String ownerAccountId, String deviceId) {
        List<String> mediaAccountIds = mediaAccountRepository.findByOwnerAccountId(ownerAccountId).stream()
                .map(MediaAccount::getId)
                .toList();
        if (mediaAccountIds.isEmpty()) {
            return Optional.empty();
        }
        return taskRepository.findFirstByStatusAndMediaAccountIdInOrderByPriorityDescCreatedAtAsc(
                        DistributionTaskStatus.PENDING,
                        mediaAccountIds
                )
                .map(task -> claim(task, deviceId));
    }

    public Optional<DistributionTask> prepareAndClaimForOwner(String ownerAccountId, String deviceId) {
        generateTasksForOwner(ownerAccountId);
        return claimForOwner(ownerAccountId, deviceId);
    }

    public DistributionTask prioritizeDramaForOwner(String ownerAccountId, String dramaId) {
        var drama = dramaRepository.findById(dramaId)
                .orElseThrow(() -> new BusinessException("DRAMA_NOT_FOUND", "短剧不存在", HttpStatus.NOT_FOUND));
        if (drama.getStatus() != DramaStatus.READY) {
            throw new BusinessException("DRAMA_NOT_READY", "短剧不可分发", HttpStatus.BAD_REQUEST);
        }
        List<String> ownedMediaAccountIds = mediaAccountRepository.findByOwnerAccountId(ownerAccountId).stream()
                .map(MediaAccount::getId)
                .toList();
        if (!ownedMediaAccountIds.isEmpty()) {
            Optional<DistributionTask> pendingTask = taskRepository.findFirstByDramaIdAndStatusAndMediaAccountIdInOrderByCreatedAtAsc(
                    dramaId,
                    DistributionTaskStatus.PENDING,
                    ownedMediaAccountIds
            );
            if (pendingTask.isPresent()) {
                DistributionTask task = pendingTask.get();
                task.setPriority(100);
                return taskRepository.save(task);
            }
        }
        if (taskRepository.existsActiveByDramaId(dramaId)) {
            throw new BusinessException("DRAMA_ALREADY_DISTRIBUTING", "这部剧已经有分发任务", HttpStatus.CONFLICT);
        }
        return mediaAccountRepository.findByOwnerAccountId(ownerAccountId).stream()
                .filter(this::hasSavedLoginState)
                .filter(media -> planner.canDistribute(media, drama))
                .findFirst()
                .map(media -> createTask(media.getId(), dramaId, 100))
                .orElseThrow(() -> new BusinessException("NO_ELIGIBLE_MEDIA_ACCOUNT", "没有可用媒体号可分发这部剧", HttpStatus.BAD_REQUEST));
    }

    private List<DistributionTask> generateTasksForMediaAccounts(List<MediaAccount> mediaAccounts, List<com.onehot.aidrama.dramas.Drama> dramas) {
        return dramas.stream()
                .filter(drama -> !taskRepository.existsActiveByDramaId(drama.getId()))
                .flatMap(drama -> mediaAccounts.stream()
                        .filter(media -> hasSavedLoginState(media))
                        .filter(media -> planner.canDistribute(media, drama))
                        .findFirst()
                        .stream()
                        .map(media -> createTask(media.getId(), drama.getId(), 0)))
                .toList();
    }

    private boolean hasSavedLoginState(MediaAccount media) {
        return media.getLoginStateRef() != null && !media.getLoginStateRef().isBlank();
    }

    private DistributionTask claim(DistributionTask task, String deviceId) {
        task.setStatus(DistributionTaskStatus.CLAIMED);
        task.setLockedByDeviceId(deviceId);
        return taskRepository.save(task);
    }

    private DistributionTask createTask(String mediaAccountId, String dramaId, int priority) {
        DistributionTask task = new DistributionTask();
        task.setMediaAccountId(mediaAccountId);
        task.setDramaId(dramaId);
        task.setStatus(DistributionTaskStatus.PENDING);
        task.setPriority(priority);
        return taskRepository.save(task);
    }
}
