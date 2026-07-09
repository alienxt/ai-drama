package com.onehot.aidrama.distribution;

import com.onehot.aidrama.baiduyun.BaiduDramaPreparationService;
import com.onehot.aidrama.common.PageResult;
import com.onehot.aidrama.common.error.BusinessException;
import com.onehot.aidrama.dramas.Drama;
import com.onehot.aidrama.dramas.DramaRepository;
import com.onehot.aidrama.dramas.DramaStatus;
import com.onehot.aidrama.media.MediaAccount;
import com.onehot.aidrama.media.MediaAccountRepository;
import com.onehot.aidrama.users.Account;
import com.onehot.aidrama.users.AccountRepository;
import org.bson.types.ObjectId;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.task.TaskExecutor;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.function.Function;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

@Service
public class DistributionService {
    private static final Duration ACTIVE_TASK_RETRY_GRACE = Duration.ofMinutes(15);
    private static final Duration PREPARATION_FAILURE_GRACE = Duration.ofMinutes(10);
    private static final int PREPARATION_RETRY_AFTER_SECONDS = 3;
    private static final String PREPARATION_FAILURE_PREFIX = "AI 素材生成失败：";
    private static final String FORCE_STOP_FAILURE_REASON = "用户强制停止任务";
    private static final int DAILY_PUBLISH_LIMIT = 10;
    private static final ZoneId DAILY_PUBLISH_LIMIT_ZONE = ZoneId.of("Asia/Shanghai");
    private static final List<DistributionTaskStatus> ACTIVE_TASK_STATUSES = List.of(
            DistributionTaskStatus.CLAIMED,
            DistributionTaskStatus.DOWNLOADING,
            DistributionTaskStatus.PROCESSING,
            DistributionTaskStatus.UPLOADING
    );
    private static final List<DistributionTaskStatus> DAILY_PUBLISH_COUNT_STATUSES = List.of(
            DistributionTaskStatus.CLAIMED,
            DistributionTaskStatus.DOWNLOADING,
            DistributionTaskStatus.PROCESSING,
            DistributionTaskStatus.UPLOADING,
            DistributionTaskStatus.SUCCEEDED,
            DistributionTaskStatus.FAILED,
            DistributionTaskStatus.CANCELLED
    );
    private final DramaRepository dramaRepository;
    private final MediaAccountRepository mediaAccountRepository;
    private final DistributionTaskRepository taskRepository;
    private final AccountRepository accountRepository;
    private final MongoTemplate mongoTemplate;
    private final BaiduDramaPreparationService preparationService;
    private final TaskExecutor taskExecutor;
    private final DistributionPlanner planner = new DistributionPlanner();
    private final ConcurrentMap<String, Object> preparationLocks = new ConcurrentHashMap<>();

    @Autowired
    public DistributionService(
            DramaRepository dramaRepository,
            MediaAccountRepository mediaAccountRepository,
            DistributionTaskRepository taskRepository,
            AccountRepository accountRepository,
            MongoTemplate mongoTemplate,
            BaiduDramaPreparationService preparationService,
            TaskExecutor taskExecutor
    ) {
        this.dramaRepository = dramaRepository;
        this.mediaAccountRepository = mediaAccountRepository;
        this.taskRepository = taskRepository;
        this.accountRepository = accountRepository;
        this.mongoTemplate = mongoTemplate;
        this.preparationService = preparationService;
        this.taskExecutor = taskExecutor;
    }

    public DistributionService(
            DramaRepository dramaRepository,
            MediaAccountRepository mediaAccountRepository,
            DistributionTaskRepository taskRepository,
            AccountRepository accountRepository,
            MongoTemplate mongoTemplate
    ) {
        this(dramaRepository, mediaAccountRepository, taskRepository, accountRepository, mongoTemplate, null, null);
    }

    DistributionService(
            DramaRepository dramaRepository,
            MediaAccountRepository mediaAccountRepository,
            DistributionTaskRepository taskRepository
    ) {
        this(dramaRepository, mediaAccountRepository, taskRepository, null, null, null, null);
    }

    DistributionService(
            DramaRepository dramaRepository,
            MediaAccountRepository mediaAccountRepository,
            DistributionTaskRepository taskRepository,
            BaiduDramaPreparationService preparationService
    ) {
        this(dramaRepository, mediaAccountRepository, taskRepository, null, null, preparationService, null);
    }

    DistributionService(
            DramaRepository dramaRepository,
            MediaAccountRepository mediaAccountRepository,
            DistributionTaskRepository taskRepository,
            BaiduDramaPreparationService preparationService,
            TaskExecutor taskExecutor
    ) {
        this(dramaRepository, mediaAccountRepository, taskRepository, null, null, preparationService, taskExecutor);
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

    public List<DistributionDtos.TaskStatusCount> adminTaskStatusCounts(String keyword) {
        Map<DistributionTaskStatus, Long> counts = countAdminTasksByStatus(keyword);
        return Arrays.stream(DistributionTaskStatus.values())
                .map(status -> new DistributionDtos.TaskStatusCount(status, counts.getOrDefault(status, 0L)))
                .toList();
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
        Map<String, MediaAccount> mediaById = mediaAccountsById(taskPage.getContent());
        Map<String, com.onehot.aidrama.dramas.Drama> dramaById = dramasById(taskPage.getContent());
        Map<String, Account> ownerById = ownerAccountsById(mediaById);
        var rows = taskPage.getContent().stream().map(task -> {
            MediaAccount mediaAccount = mediaById.get(task.getMediaAccountId());
            String ownerAccountId = mediaAccount == null ? null : mediaAccount.getOwnerAccountId();
            String ownerUsername = ownerAccountId == null
                    ? null
                    : Optional.ofNullable(ownerById.get(ownerAccountId))
                            .map(Account::getUsername)
                            .orElse(ownerAccountId);
            return DistributionDtos.AdminTaskResponse.from(
                    task,
                    ownerAccountId,
                    ownerUsername,
                    Optional.ofNullable(mediaAccount)
                            .map(MediaAccount::getDisplayName)
                            .orElse(task.getMediaAccountId()),
                    Optional.ofNullable(dramaById.get(task.getDramaId()))
                            .map(this::dramaDisplayTitle)
                            .orElse(task.getDramaId())
            );
        }).toList();
        return PageResult.from(new PageImpl<>(rows, taskPage.getPageable(), taskPage.getTotalElements()));
    }

    private Map<String, Account> ownerAccountsById(Map<String, MediaAccount> mediaById) {
        if (accountRepository == null || mediaById.isEmpty()) {
            return Map.of();
        }
        List<String> ownerAccountIds = mediaById.values().stream()
                .map(MediaAccount::getOwnerAccountId)
                .filter(value -> value != null && !value.isBlank())
                .distinct()
                .toList();
        if (ownerAccountIds.isEmpty()) {
            return Map.of();
        }
        return accountRepository.findAllById(ownerAccountIds).stream()
                .collect(Collectors.toMap(Account::getId, Function.identity()));
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

    private Map<DistributionTaskStatus, Long> countAdminTasksByStatus(String keyword) {
        EnumMap<DistributionTaskStatus, Long> counts = new EnumMap<>(DistributionTaskStatus.class);
        if (mongoTemplate == null) {
            List<DistributionTask> tasks = taskRepository.findAll();
            Map<String, MediaAccount> mediaById = mediaAccountsById(tasks);
            Map<String, com.onehot.aidrama.dramas.Drama> dramaById = dramasById(tasks);
            tasks.stream()
                    .filter(task -> fallbackKeywordMatches(
                            task,
                            keyword,
                            mediaById.get(task.getMediaAccountId()),
                            dramaById.get(task.getDramaId())
                    ))
                    .forEach(task -> incrementStatusCount(counts, task.getStatus()));
            return counts;
        }
        Query query = new Query();
        Optional.ofNullable(keywordCriteria(keyword)).ifPresent(query::addCriteria);
        mongoTemplate.find(query, DistributionTask.class)
                .forEach(task -> incrementStatusCount(counts, task.getStatus()));
        return counts;
    }

    private void incrementStatusCount(Map<DistributionTaskStatus, Long> counts, DistributionTaskStatus status) {
        if (status != null) {
            counts.merge(status, 1L, Long::sum);
        }
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
            List<DistributionTask> tasks = taskRepository.findAll();
            Map<String, MediaAccount> mediaById = mediaAccountsById(tasks);
            Map<String, com.onehot.aidrama.dramas.Drama> dramaById = dramasById(tasks);
            List<DistributionTask> filtered = tasks.stream()
                    .filter(task -> status == null || task.getStatus() == status)
                    .filter(task -> mediaAccountIds == null || mediaAccountIds.contains(task.getMediaAccountId()))
                    .filter(task -> fallbackKeywordMatches(
                            task,
                            keyword,
                            mediaById.get(task.getMediaAccountId()),
                            dramaById.get(task.getDramaId())
                    ))
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

    private Map<String, MediaAccount> mediaAccountsById(List<DistributionTask> tasks) {
        List<String> mediaAccountIds = tasks.stream()
                .map(DistributionTask::getMediaAccountId)
                .filter(value -> value != null && !value.isBlank())
                .distinct()
                .toList();
        if (mediaAccountIds.isEmpty()) {
            return Map.of();
        }
        return mediaAccountRepository.findAllById(mediaAccountIds).stream()
                .collect(Collectors.toMap(MediaAccount::getId, Function.identity()));
    }

    private Map<String, com.onehot.aidrama.dramas.Drama> dramasById(List<DistributionTask> tasks) {
        List<String> dramaIds = tasks.stream()
                .map(DistributionTask::getDramaId)
                .filter(value -> value != null && !value.isBlank())
                .distinct()
                .toList();
        if (dramaIds.isEmpty()) {
            return Map.of();
        }
        return dramaRepository.findAllById(dramaIds).stream()
                .collect(Collectors.toMap(com.onehot.aidrama.dramas.Drama::getId, Function.identity()));
    }

    private boolean fallbackKeywordMatches(
            DistributionTask task,
            String keyword,
            MediaAccount mediaAccount,
            com.onehot.aidrama.dramas.Drama drama
    ) {
        if (keyword == null || keyword.isBlank()) {
            return true;
        }
        String clean = keyword.trim().toLowerCase();
        return containsIgnoreCase(task.getId(), clean)
                || containsIgnoreCase(task.getMediaAccountId(), clean)
                || containsIgnoreCase(task.getDramaId(), clean)
                || containsIgnoreCase(task.getFailureReason(), clean)
                || containsIgnoreCase(mediaAccount == null ? null : mediaAccount.getDisplayName(), clean)
                || containsIgnoreCase(mediaAccount == null ? null : mediaAccount.getExternalAccountId(), clean)
                || containsIgnoreCase(mediaAccount == null ? null : mediaAccount.getOwnerAccountId(), clean)
                || containsIgnoreCase(drama == null ? null : drama.getTitle(), clean)
                || containsIgnoreCase(drama == null ? null : drama.getAiTitle(), clean);
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
        List<String> ownerMediaAccountIds = matchingOwnerMediaAccountIds(clean);
        if (!ownerMediaAccountIds.isEmpty()) {
            criteria.add(Criteria.where("mediaAccountId").in(ownerMediaAccountIds));
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
                Criteria.where("externalAccountId").regex(pattern),
                Criteria.where("ownerAccountId").is(keyword)
        )).limit(200);
        return mongoTemplate.find(query, MediaAccount.class).stream()
                .map(MediaAccount::getId)
                .toList();
    }

    private List<String> matchingOwnerMediaAccountIds(String keyword) {
        Pattern pattern = Pattern.compile(Pattern.quote(keyword), Pattern.CASE_INSENSITIVE);
        Query accountQuery = new Query(Criteria.where("username").regex(pattern)).limit(200);
        List<String> ownerAccountIds = mongoTemplate.find(accountQuery, Account.class).stream()
                .map(Account::getId)
                .toList();
        if (ownerAccountIds.isEmpty()) {
            return List.of();
        }
        Query mediaQuery = new Query(Criteria.where("ownerAccountId").in(ownerAccountIds)).limit(500);
        return mongoTemplate.find(mediaQuery, MediaAccount.class).stream()
                .map(MediaAccount::getId)
                .toList();
    }

    private List<String> matchingDramaIds(String keyword) {
        Pattern pattern = Pattern.compile(Pattern.quote(keyword), Pattern.CASE_INSENSITIVE);
        Query query = new Query(new Criteria().orOperator(
                Criteria.where("title").regex(pattern),
                Criteria.where("aiTitle").regex(pattern),
                Criteria.where("aiTitleEn").regex(pattern),
                Criteria.where("aiSummary").regex(pattern),
                Criteria.where("aiSummaryEn").regex(pattern)
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
        return claimForOwner(ownerAccountId, deviceId, false);
    }

    public Optional<DistributionTask> claimForOwner(String ownerAccountId, String deviceId, boolean asyncPreparation) {
        List<String> mediaAccountIds = mediaAccountRepository.findByOwnerAccountId(ownerAccountId).stream()
                .map(MediaAccount::getId)
                .toList();
        if (mediaAccountIds.isEmpty()) {
            return Optional.empty();
        }
        assertDailyPublishLimitAvailable(mediaAccountIds);
        return taskRepository.findFirstByStatusAndMediaAccountIdInOrderByPriorityDescCreatedAtAsc(
                        DistributionTaskStatus.PENDING,
                        mediaAccountIds
                )
                .map(task -> prepareAndClaim(task, deviceId, asyncPreparation));
    }

    public Optional<DistributionTask> prepareAndClaimForOwner(String ownerAccountId, String deviceId) {
        return prepareAndClaimForOwner(ownerAccountId, deviceId, false);
    }

    public Optional<DistributionTask> prepareAndClaimForOwner(String ownerAccountId, String deviceId, boolean asyncPreparation) {
        Optional<DistributionTask> pendingTask = claimForOwner(ownerAccountId, deviceId, asyncPreparation);
        if (pendingTask.isPresent()) {
            return pendingTask;
        }
        return generateNextTaskForOwner(ownerAccountId)
                .map(task -> prepareAndClaim(task, deviceId, asyncPreparation));
    }

    private Optional<DistributionTask> generateNextTaskForOwner(String ownerAccountId) {
        var dramas = recentReadyDramas();
        var mediaAccounts = mediaAccountRepository.findByOwnerAccountId(ownerAccountId);
        for (var drama : dramas) {
            for (var media : mediaAccounts) {
                if (hasSavedLoginState(media)
                        && planner.canDistribute(media, drama)
                        && !hasBlockingGeneratedTask(media.getId(), drama.getId())) {
                    return Optional.of(createTask(media.getId(), drama.getId(), 0));
                }
            }
        }
        return Optional.empty();
    }

    public DistributionTask retryAndClaimForOwner(String ownerAccountId, String taskId, String deviceId) {
        return retryAndClaimForOwner(ownerAccountId, taskId, deviceId, false);
    }

    public DistributionTask retryAndClaimForOwner(String ownerAccountId, String taskId, String deviceId, boolean asyncPreparation) {
        List<String> mediaAccountIds = ownerMediaAccountIds(ownerAccountId);
        DistributionTask task = taskRepository.findById(taskId)
                .orElseThrow(() -> new BusinessException("TASK_NOT_FOUND", "任务不存在", HttpStatus.NOT_FOUND));
        if (!mediaAccountIds.contains(task.getMediaAccountId())) {
            throw new BusinessException("TASK_NOT_FOUND", "任务不存在", HttpStatus.NOT_FOUND);
        }
        if (!isRetryableFromDesktop(task.getStatus())) {
            throw new BusinessException(
                    "TASK_NOT_RETRYABLE",
                    "只有失败、已取消或执行中的任务可以重试",
                    HttpStatus.BAD_REQUEST
            );
        }
        if (isActiveTaskRecentlyUpdated(task)) {
            throw activeTaskStillRunningException();
        }
        assertDailyPublishLimitAvailable(mediaAccountIds);
        clearTaskForRetry(task);
        return prepareAndClaim(task, deviceId, asyncPreparation);
    }

    private void assertDailyPublishLimitAvailable(List<String> mediaAccountIds) {
        long todayCount = taskRepository.countByMediaAccountIdInAndUpdatedAtGreaterThanEqualAndStatusIn(
                mediaAccountIds,
                publishLimitDayStart(),
                DAILY_PUBLISH_COUNT_STATUSES
        );
        if (todayCount >= DAILY_PUBLISH_LIMIT) {
            throw new BusinessException(
                    "DAILY_PUBLISH_LIMIT_REACHED",
                    "今日发布次数已达 " + DAILY_PUBLISH_LIMIT + " 次，请明天再发布。",
                    HttpStatus.TOO_MANY_REQUESTS
            );
        }
    }

    private Instant publishLimitDayStart() {
        return ZonedDateTime.now(DAILY_PUBLISH_LIMIT_ZONE)
                .toLocalDate()
                .atStartOfDay(DAILY_PUBLISH_LIMIT_ZONE)
                .toInstant();
    }

    private boolean isRetryableFromDesktop(DistributionTaskStatus status) {
        return switch (status) {
            case FAILED, CANCELLED, CLAIMED, DOWNLOADING, PROCESSING, UPLOADING -> true;
            case PENDING, SUCCEEDED -> false;
        };
    }

    private boolean isActiveTaskRecentlyUpdated(DistributionTask task) {
        if (!ACTIVE_TASK_STATUSES.contains(task.getStatus())) {
            return false;
        }
        Instant updatedAt = task.getUpdatedAt();
        return updatedAt != null && updatedAt.isAfter(Instant.now().minus(ACTIVE_TASK_RETRY_GRACE));
    }

    public DistributionTask retryTaskFromAdmin(String taskId) {
        DistributionTask task = taskRepository.findById(taskId)
                .orElseThrow(() -> new BusinessException("TASK_NOT_FOUND", "任务不存在", HttpStatus.NOT_FOUND));
        if (isActiveTaskRecentlyUpdated(task)) {
            throw activeTaskStillRunningException();
        }
        clearTaskForRetry(task);
        task.setStatus(DistributionTaskStatus.PENDING);
        return taskRepository.save(task);
    }

    private void clearTaskForRetry(DistributionTask task) {
        task.setProgress(0);
        task.setLockedByDeviceId(null);
        task.setFailureReason(null);
        task.setPlatformPublishId(null);
        task.setFinishedAt(null);
    }

    private BusinessException activeTaskStillRunningException() {
        return new BusinessException(
                "TASK_STILL_RUNNING",
                "任务仍在执行中，请先暂停/跳过，或等待长时间无进度后再重试",
                HttpStatus.CONFLICT
        );
    }

    public DistributionTask releaseTaskForOwner(String ownerAccountId, String taskId) {
        List<String> mediaAccountIds = ownerMediaAccountIds(ownerAccountId);
        DistributionTask task = taskRepository.findById(taskId)
                .orElseThrow(() -> new BusinessException("TASK_NOT_FOUND", "任务不存在", HttpStatus.NOT_FOUND));
        if (!mediaAccountIds.contains(task.getMediaAccountId())) {
            throw new BusinessException("TASK_NOT_FOUND", "任务不存在", HttpStatus.NOT_FOUND);
        }
        task.setStatus(DistributionTaskStatus.PENDING);
        task.setProgress(0);
        task.setLockedByDeviceId(null);
        task.setFailureReason(null);
        task.setPlatformPublishId(null);
        task.setFinishedAt(null);
        return taskRepository.save(task);
    }

    public DistributionTask forceStopTaskForOwner(String ownerAccountId, String taskId) {
        List<String> mediaAccountIds = ownerMediaAccountIds(ownerAccountId);
        DistributionTask task = taskRepository.findById(taskId)
                .orElseThrow(() -> new BusinessException("TASK_NOT_FOUND", "任务不存在", HttpStatus.NOT_FOUND));
        if (!mediaAccountIds.contains(task.getMediaAccountId())) {
            throw new BusinessException("TASK_NOT_FOUND", "任务不存在", HttpStatus.NOT_FOUND);
        }
        if (task.getStatus() == DistributionTaskStatus.CANCELLED) {
            return task;
        }
        if (!isForceStoppable(task.getStatus())) {
            throw new BusinessException(
                    "TASK_NOT_RUNNING",
                    "只有待执行或执行中的任务可以强制停止",
                    HttpStatus.BAD_REQUEST
            );
        }
        task.setStatus(DistributionTaskStatus.CANCELLED);
        task.setLockedByDeviceId(null);
        task.setFailureReason(FORCE_STOP_FAILURE_REASON);
        task.setFinishedAt(Instant.now());
        return taskRepository.save(task);
    }

    private boolean isForceStoppable(DistributionTaskStatus status) {
        return status == DistributionTaskStatus.PENDING || ACTIVE_TASK_STATUSES.contains(status);
    }

    public DistributionDtos.PreparationResponse prepareTaskDramaForOwner(String ownerAccountId, String taskId) {
        List<String> mediaAccountIds = ownerMediaAccountIds(ownerAccountId);
        DistributionTask task = taskRepository.findById(taskId)
                .orElseThrow(() -> new BusinessException("TASK_NOT_FOUND", "任务不存在", HttpStatus.NOT_FOUND));
        if (!mediaAccountIds.contains(task.getMediaAccountId())) {
            throw new BusinessException("TASK_NOT_FOUND", "任务不存在", HttpStatus.NOT_FOUND);
        }
        if (task.getStatus() == DistributionTaskStatus.CANCELLED) {
            return preparationFailed("任务已取消");
        }
        if (task.getStatus() == DistributionTaskStatus.SUCCEEDED) {
            return preparationFailed("任务已完成，不能重新准备素材");
        }
        if (task.getStatus() == DistributionTaskStatus.FAILED && isPreparationFailureTask(task)) {
            return preparationFailed(task.getFailureReason());
        }
        if (preparationService == null) {
            return preparationFailed("AI 素材准备服务不可用");
        }
        if (task.getDramaId() == null || task.getDramaId().isBlank()) {
            return preparationFailed("任务缺少短剧 ID");
        }
        Drama drama = dramaRepository.findById(task.getDramaId())
                .orElseThrow(() -> new BusinessException("DRAMA_NOT_FOUND", "短剧不存在", HttpStatus.NOT_FOUND));
        if (isPreparedForDistribution(drama)) {
            return preparationPrepared();
        }
        if (isRecentPreparationFailure(drama)) {
            return preparationFailed("AI 素材准备失败，请检查 OpenAI 配置后重试");
        }
        Object marker = new Object();
        Object existing = preparationLocks.putIfAbsent(task.getDramaId(), marker);
        if (existing != null) {
            return preparationPreparing("AI 素材准备中，请稍候");
        }
        executePreparation(() -> prepareTaskDramaInBackground(task.getId(), task.getDramaId(), marker));
        return preparationPreparing("AI 素材准备已开始，请稍候");
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
                .filter(media -> !hasBlockingGeneratedTask(media.getId(), dramaId))
                .findFirst()
                .map(media -> createTask(media.getId(), dramaId, 100))
                .orElseThrow(() -> new BusinessException("NO_ELIGIBLE_MEDIA_ACCOUNT", "没有可用媒体号可分发这部剧", HttpStatus.BAD_REQUEST));
    }

    private List<DistributionTask> generateTasksForMediaAccounts(List<MediaAccount> mediaAccounts, List<com.onehot.aidrama.dramas.Drama> dramas) {
        return dramas.stream()
                .flatMap(drama -> mediaAccounts.stream()
                        .filter(media -> hasSavedLoginState(media))
                        .filter(media -> planner.canDistribute(media, drama))
                        .filter(media -> !hasBlockingGeneratedTask(media.getId(), drama.getId()))
                        .map(media -> createTask(media.getId(), drama.getId(), 0)))
                .toList();
    }

    private boolean hasBlockingGeneratedTask(String mediaAccountId, String dramaId) {
        return taskRepository.existsByMediaAccountIdAndDramaId(mediaAccountId, dramaId);
    }

    private boolean isPreparationFailureTask(DistributionTask task) {
        String failureReason = task.getFailureReason();
        return failureReason != null && failureReason.startsWith(PREPARATION_FAILURE_PREFIX);
    }

    private List<com.onehot.aidrama.dramas.Drama> recentReadyDramas() {
        return dramaRepository.findByStatusAndUpdatedAtGreaterThanEqual(
                DramaStatus.READY,
                recentUpdatedFrom(),
                Sort.by(Sort.Direction.DESC, "updatedAt")
        );
    }

    private boolean isPreparedForDistribution(com.onehot.aidrama.dramas.Drama drama) {
        return hasText(drama.getAiTitle())
                && hasText(drama.getAiSummary())
                && hasText(drama.getAiCoverUrl())
                && hasText(drama.getAiVideoCoverUrl())
                && !drama.isAiCoverGenerating()
                && drama.getEpisodes() != null
                && !drama.getEpisodes().isEmpty();
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

    private boolean hasText(String value) {
        return value != null && !value.isBlank();
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

    private DistributionTask prepareAndClaim(DistributionTask task, String deviceId, boolean asyncPreparation) {
        if (!asyncPreparation) {
            ensureTaskDramaPrepared(task);
        }
        return claim(task, deviceId);
    }

    private void executePreparation(Runnable runnable) {
        if (taskExecutor == null) {
            runnable.run();
            return;
        }
        taskExecutor.execute(runnable);
    }

    private void prepareTaskDramaInBackground(String taskId, String dramaId, Object marker) {
        try {
            Drama drama = dramaRepository.findById(dramaId)
                    .orElseThrow(() -> new BusinessException("DRAMA_NOT_FOUND", "短剧不存在", HttpStatus.NOT_FOUND));
            if (isPreparedForDistribution(drama)) {
                return;
            }
            Drama prepared = preparationService.prepareForDistribution(drama);
            if (!isPreparedForDistribution(prepared)) {
                markTaskPreparationFailed(taskId, "AI 剧名、AI 简介、AI 封面或视频封面生成失败，请检查 OpenAI 配置后重试");
            }
        } catch (RuntimeException exception) {
            markTaskPreparationFailed(taskId, preparationFailureMessage(exception));
        } finally {
            preparationLocks.remove(dramaId, marker);
        }
    }

    private void markTaskPreparationFailed(String taskId, String message) {
        taskRepository.findById(taskId).ifPresent(task -> {
            if (task.getStatus() == DistributionTaskStatus.CANCELLED || task.getStatus() == DistributionTaskStatus.SUCCEEDED) {
                return;
            }
            task.setStatus(DistributionTaskStatus.FAILED);
            task.setProgress(0);
            task.setLockedByDeviceId(null);
            task.setFailureReason(message.startsWith(PREPARATION_FAILURE_PREFIX) ? message : PREPARATION_FAILURE_PREFIX + message);
            task.setFinishedAt(Instant.now());
            taskRepository.save(task);
        });
    }

    private boolean isRecentPreparationFailure(Drama drama) {
        Instant failedAt = drama.getAiPreparationFailedAt();
        return failedAt != null && failedAt.isAfter(Instant.now().minus(PREPARATION_FAILURE_GRACE));
    }

    private DistributionDtos.PreparationResponse preparationPrepared() {
        return new DistributionDtos.PreparationResponse(
                true,
                false,
                false,
                "AI 素材已准备完成",
                0
        );
    }

    private DistributionDtos.PreparationResponse preparationPreparing(String message) {
        return new DistributionDtos.PreparationResponse(
                false,
                true,
                false,
                message,
                PREPARATION_RETRY_AFTER_SECONDS
        );
    }

    private DistributionDtos.PreparationResponse preparationFailed(String message) {
        return new DistributionDtos.PreparationResponse(
                false,
                false,
                true,
                message,
                0
        );
    }

    private void ensureTaskDramaPrepared(DistributionTask task) {
        if (preparationService == null || task == null || task.getDramaId() == null || task.getDramaId().isBlank()) {
            return;
        }
        Object lock = preparationLocks.computeIfAbsent(task.getDramaId(), ignored -> new Object());
        try {
            synchronized (lock) {
                Drama drama = dramaRepository.findById(task.getDramaId())
                        .orElseThrow(() -> new BusinessException("DRAMA_NOT_FOUND", "短剧不存在", HttpStatus.NOT_FOUND));
                if (isPreparedForDistribution(drama)) {
                    return;
                }
                Drama prepared = preparationService.prepareForDistribution(drama);
                if (!isPreparedForDistribution(prepared)) {
                    throw new BusinessException(
                            "DRAMA_PREPARATION_FAILED",
                            "AI 剧名、AI 简介、AI 封面或视频封面生成失败，请检查 OpenAI 配置后重试",
                            HttpStatus.BAD_GATEWAY
                    );
                }
            }
        } catch (RuntimeException exception) {
            markTaskPreparationFailed(task, exception);
            throw exception;
        } finally {
            preparationLocks.remove(task.getDramaId(), lock);
        }
    }

    private void markTaskPreparationFailed(DistributionTask task, RuntimeException exception) {
        task.setStatus(DistributionTaskStatus.FAILED);
        task.setProgress(0);
        task.setLockedByDeviceId(null);
        task.setFailureReason(preparationFailureMessage(exception));
        task.setFinishedAt(Instant.now());
        taskRepository.save(task);
    }

    private String preparationFailureMessage(RuntimeException exception) {
        String message = exception.getMessage();
        if (message == null || message.isBlank()) {
            message = exception.getClass().getSimpleName();
        }
        return PREPARATION_FAILURE_PREFIX + message;
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
