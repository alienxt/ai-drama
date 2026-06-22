package com.onehot.aidrama.distribution;

import com.onehot.aidrama.common.PageResult;
import com.onehot.aidrama.common.error.BusinessException;
import com.onehot.aidrama.dramas.DramaRepository;
import com.onehot.aidrama.dramas.DramaStatus;
import com.onehot.aidrama.media.MediaAccount;
import com.onehot.aidrama.media.MediaAccountRepository;
import org.bson.types.ObjectId;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.Function;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

@Service
public class DistributionService {
    private final DramaRepository dramaRepository;
    private final MediaAccountRepository mediaAccountRepository;
    private final DistributionTaskRepository taskRepository;
    private final MongoTemplate mongoTemplate;
    private final DistributionPlanner planner = new DistributionPlanner();

    @Autowired
    public DistributionService(
            DramaRepository dramaRepository,
            MediaAccountRepository mediaAccountRepository,
            DistributionTaskRepository taskRepository,
            MongoTemplate mongoTemplate
    ) {
        this.dramaRepository = dramaRepository;
        this.mediaAccountRepository = mediaAccountRepository;
        this.taskRepository = taskRepository;
        this.mongoTemplate = mongoTemplate;
    }

    DistributionService(
            DramaRepository dramaRepository,
            MediaAccountRepository mediaAccountRepository,
            DistributionTaskRepository taskRepository
    ) {
        this(dramaRepository, mediaAccountRepository, taskRepository, null);
    }

    public List<DistributionTask> generateTasks() {
        var dramas = recentReadyDramas();
        var mediaAccounts = mediaAccountRepository.findAll();
        return generateTasksForMediaAccounts(mediaAccounts, dramas);
    }

    public PageResult<DistributionDtos.AdminTaskResponse> listAdminTasks(Pageable pageable) {
        return listAdminTasks(null, null, pageable);
    }

    public PageResult<DistributionDtos.AdminTaskResponse> listAdminTasks(
            String keyword,
            DistributionTaskStatus status,
            Pageable pageable
    ) {
        return taskResponsePage(findTasks(keyword, status, pageable, null));
    }

    public PageResult<DistributionDtos.AdminTaskResponse> listDesktopTasks(
            String ownerAccountId,
            String keyword,
            DistributionTaskStatus status,
            Pageable pageable
    ) {
        List<String> mediaAccountIds = ownerMediaAccountIds(ownerAccountId);
        if (mediaAccountIds.isEmpty()) {
            return PageResult.from(new PageImpl<>(List.of(), pageable, 0));
        }
        return taskResponsePage(findTasks(keyword, status, pageable, mediaAccountIds));
    }

    private PageResult<DistributionDtos.AdminTaskResponse> taskResponsePage(PageImpl<DistributionTask> taskPage) {
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
                Optional.ofNullable(mediaById.get(task.getMediaAccountId()))
                        .map(MediaAccount::getDisplayName)
                        .orElse(task.getMediaAccountId()),
                Optional.ofNullable(dramaById.get(task.getDramaId()))
                        .map(this::dramaDisplayTitle)
                        .orElse(task.getDramaId())
        )).toList();
        return PageResult.from(new PageImpl<>(rows, taskPage.getPageable(), taskPage.getTotalElements()));
    }

    private String dramaDisplayTitle(com.onehot.aidrama.dramas.Drama drama) {
        if (drama.getAiTitle() != null && !drama.getAiTitle().isBlank()) {
            return drama.getAiTitle();
        }
        return drama.getTitle();
    }

    private PageImpl<DistributionTask> findAdminTasks(
            String keyword,
            DistributionTaskStatus status,
            Pageable pageable
    ) {
        return findTasks(keyword, status, pageable, null);
    }

    private PageImpl<DistributionTask> findTasks(
            String keyword,
            DistributionTaskStatus status,
            Pageable pageable,
            List<String> mediaAccountIds
    ) {
        if (mediaAccountIds != null && mediaAccountIds.isEmpty()) {
            return new PageImpl<>(List.of(), pageable, 0);
        }
        if (mongoTemplate == null) {
            if ((keyword == null || keyword.isBlank()) && status == null && mediaAccountIds == null) {
                var page = taskRepository.findAll(pageable);
                return new PageImpl<>(page.getContent(), page.getPageable(), page.getTotalElements());
            }
            List<DistributionTask> filtered = taskRepository.findAll().stream()
                    .filter(task -> status == null || task.getStatus() == status)
                    .filter(task -> mediaAccountIds == null || mediaAccountIds.contains(task.getMediaAccountId()))
                    .filter(task -> fallbackKeywordMatches(task, keyword))
                    .toList();
            int start = (int) Math.min(pageable.getOffset(), filtered.size());
            int end = Math.min(start + pageable.getPageSize(), filtered.size());
            return new PageImpl<>(filtered.subList(start, end), pageable, filtered.size());
        }
        var effectivePageable = pageable.getSort().isSorted()
                ? pageable
                : PageRequest.of(
                        pageable.getPageNumber(),
                        pageable.getPageSize(),
                        Sort.by(Sort.Direction.DESC, "createdAt")
                );
        Query query = new Query();
        List<Criteria> criteria = new ArrayList<>();
        if (mediaAccountIds != null) {
            criteria.add(Criteria.where("mediaAccountId").in(mediaAccountIds));
        }
        if (status != null) {
            criteria.add(Criteria.where("status").is(status));
        }
        Optional.ofNullable(keywordCriteria(keyword)).ifPresent(criteria::add);
        if (!criteria.isEmpty()) {
            query.addCriteria(criteria.size() == 1 ? criteria.getFirst() : new Criteria().andOperator(criteria));
        }
        long total = mongoTemplate.count(query, DistributionTask.class);
        var tasks = mongoTemplate.find(query.with(effectivePageable), DistributionTask.class);
        return new PageImpl<>(tasks, effectivePageable, total);
    }

    private boolean fallbackKeywordMatches(DistributionTask task, String keyword) {
        if (keyword == null || keyword.isBlank()) {
            return true;
        }
        String clean = keyword.trim().toLowerCase();
        return containsIgnoreCase(task.getId(), clean)
                || containsIgnoreCase(task.getMediaAccountId(), clean)
                || containsIgnoreCase(task.getDramaId(), clean)
                || containsIgnoreCase(task.getFailureReason(), clean);
    }

    private boolean containsIgnoreCase(String value, String cleanKeyword) {
        return value != null && value.toLowerCase().contains(cleanKeyword);
    }

    private Criteria keywordCriteria(String keyword) {
        if (keyword == null || keyword.isBlank()) {
            return null;
        }
        String clean = keyword.trim();
        List<Criteria> criteria = new ArrayList<>();
        if (ObjectId.isValid(clean)) {
            criteria.add(Criteria.where("_id").is(new ObjectId(clean)));
        }
        criteria.add(Criteria.where("mediaAccountId").is(clean));
        criteria.add(Criteria.where("dramaId").is(clean));
        List<String> mediaAccountIds = matchingMediaAccountIds(clean);
        if (!mediaAccountIds.isEmpty()) {
            criteria.add(Criteria.where("mediaAccountId").in(mediaAccountIds));
        }
        List<String> dramaIds = matchingDramaIds(clean);
        if (!dramaIds.isEmpty()) {
            criteria.add(Criteria.where("dramaId").in(dramaIds));
        }
        if (criteria.isEmpty()) {
            return Criteria.where("_id").exists(false);
        }
        return new Criteria().orOperator(criteria);
    }

    private List<String> matchingMediaAccountIds(String keyword) {
        Pattern pattern = Pattern.compile(Pattern.quote(keyword), Pattern.CASE_INSENSITIVE);
        Query query = new Query(new Criteria().orOperator(
                Criteria.where("displayName").regex(pattern),
                Criteria.where("externalAccountId").regex(pattern)
        )).limit(200);
        return mongoTemplate.find(query, MediaAccount.class).stream()
                .map(MediaAccount::getId)
                .toList();
    }

    private List<String> matchingDramaIds(String keyword) {
        Pattern pattern = Pattern.compile(Pattern.quote(keyword), Pattern.CASE_INSENSITIVE);
        Query query = new Query(new Criteria().orOperator(
                Criteria.where("title").regex(pattern),
                Criteria.where("aiTitle").regex(pattern)
        )).limit(200);
        return mongoTemplate.find(query, com.onehot.aidrama.dramas.Drama.class).stream()
                .map(com.onehot.aidrama.dramas.Drama::getId)
                .toList();
    }

    public List<DistributionTask> generateTasksForOwner(String ownerAccountId) {
        var dramas = recentReadyDramas();
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

    public DistributionTask retryAndClaimForOwner(String ownerAccountId, String taskId, String deviceId) {
        List<String> mediaAccountIds = ownerMediaAccountIds(ownerAccountId);
        DistributionTask task = taskRepository.findById(taskId)
                .orElseThrow(() -> new BusinessException("TASK_NOT_FOUND", "任务不存在", HttpStatus.NOT_FOUND));
        if (!mediaAccountIds.contains(task.getMediaAccountId())) {
            throw new BusinessException("TASK_NOT_FOUND", "任务不存在", HttpStatus.NOT_FOUND);
        }
        if (task.getStatus() != DistributionTaskStatus.FAILED && task.getStatus() != DistributionTaskStatus.CANCELLED) {
            throw new BusinessException(
                    "TASK_NOT_RETRYABLE",
                    "只有失败或已取消任务可以重试",
                    HttpStatus.BAD_REQUEST
            );
        }
        task.setProgress(0);
        task.setLockedByDeviceId(null);
        task.setFailureReason(null);
        task.setPlatformPublishId(null);
        task.setFinishedAt(null);
        return claim(task, deviceId);
    }

    public DistributionTask prioritizeDramaForOwner(String ownerAccountId, String dramaId) {
        var drama = dramaRepository.findById(dramaId)
                .orElseThrow(() -> new BusinessException("DRAMA_NOT_FOUND", "短剧不存在", HttpStatus.NOT_FOUND));
        if (drama.getStatus() != DramaStatus.READY) {
            throw new BusinessException("DRAMA_NOT_READY", "短剧不可分发", HttpStatus.BAD_REQUEST);
        }
        if (!isRecentUpdatedDrama(drama)) {
            throw new BusinessException("DRAMA_NOT_IN_RECENT_POOL", "短剧不在最近更新剧池内", HttpStatus.BAD_REQUEST);
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
        return mediaAccountRepository.findByOwnerAccountId(ownerAccountId).stream()
                .filter(this::hasSavedLoginState)
                .filter(media -> planner.canDistribute(media, drama))
                .filter(media -> !taskRepository.existsByMediaAccountIdAndDramaId(media.getId(), dramaId))
                .findFirst()
                .map(media -> createTask(media.getId(), dramaId, 100))
                .orElseThrow(() -> new BusinessException("NO_ELIGIBLE_MEDIA_ACCOUNT", "没有可用媒体号可分发这部剧", HttpStatus.BAD_REQUEST));
    }

    private List<DistributionTask> generateTasksForMediaAccounts(List<MediaAccount> mediaAccounts, List<com.onehot.aidrama.dramas.Drama> dramas) {
        return dramas.stream()
                .flatMap(drama -> mediaAccounts.stream()
                        .filter(media -> hasSavedLoginState(media))
                        .filter(media -> planner.canDistribute(media, drama))
                        .filter(media -> !taskRepository.existsByMediaAccountIdAndDramaId(media.getId(), drama.getId()))
                        .map(media -> createTask(media.getId(), drama.getId(), 0)))
                .toList();
    }

    private List<com.onehot.aidrama.dramas.Drama> recentReadyDramas() {
        return dramaRepository.findByStatusAndUpdatedAtGreaterThanEqual(
                DramaStatus.READY,
                recentUpdatedFrom(),
                Sort.by(Sort.Direction.DESC, "updatedAt")
        );
    }

    private boolean isRecentUpdatedDrama(com.onehot.aidrama.dramas.Drama drama) {
        return drama.getUpdatedAt() != null && !drama.getUpdatedAt().isBefore(recentUpdatedFrom());
    }

    private Instant recentUpdatedFrom() {
        return Instant.now().minus(7, ChronoUnit.DAYS);
    }

    private boolean hasSavedLoginState(MediaAccount media) {
        return media.getLoginStateRef() != null && !media.getLoginStateRef().isBlank();
    }

    private List<String> ownerMediaAccountIds(String ownerAccountId) {
        return mediaAccountRepository.findByOwnerAccountId(ownerAccountId).stream()
                .map(MediaAccount::getId)
                .toList();
    }

    private DistributionTask claim(DistributionTask task, String deviceId) {
        task.setStatus(DistributionTaskStatus.CLAIMED);
        task.setLockedByDeviceId(deviceId);
        task.setFinishedAt(null);
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
