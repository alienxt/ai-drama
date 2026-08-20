package com.onehot.aidrama.users;

import com.onehot.aidrama.common.MongoPageQuery;
import com.onehot.aidrama.common.error.BusinessException;
import com.onehot.aidrama.distribution.DistributionTaskClaimRepository;
import com.onehot.aidrama.distribution.DistributionTaskRepository;
import com.onehot.aidrama.distribution.DistributionTaskStatus;
import com.onehot.aidrama.media.MediaAccount;
import com.onehot.aidrama.media.MediaAccountRepository;
import com.onehot.aidrama.media.MediaPlatform;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.List;

@Service
public class AccountService {
    private static final ZoneId DAILY_LIMIT_ZONE = ZoneId.of("Asia/Shanghai");
    private static final List<DistributionTaskStatus> DAILY_CLAIMED_TASK_STATUSES = List.of(
            DistributionTaskStatus.CLAIMED,
            DistributionTaskStatus.DOWNLOADING,
            DistributionTaskStatus.PROCESSING,
            DistributionTaskStatus.UPLOADING,
            DistributionTaskStatus.SUCCEEDED,
            DistributionTaskStatus.FAILED,
            DistributionTaskStatus.CANCELLED
    );

    private final AccountRepository repository;
    private final PasswordEncoder passwordEncoder;
    private final MongoTemplate mongoTemplate;
    private final MediaAccountRepository mediaAccountRepository;
    private final DistributionTaskClaimRepository taskClaimRepository;
    private final DistributionTaskRepository taskRepository;

    @Autowired
    public AccountService(
            AccountRepository repository,
            PasswordEncoder passwordEncoder,
            MongoTemplate mongoTemplate,
            MediaAccountRepository mediaAccountRepository,
            DistributionTaskClaimRepository taskClaimRepository,
            DistributionTaskRepository taskRepository
    ) {
        this.repository = repository;
        this.passwordEncoder = passwordEncoder;
        this.mongoTemplate = mongoTemplate;
        this.mediaAccountRepository = mediaAccountRepository;
        this.taskClaimRepository = taskClaimRepository;
        this.taskRepository = taskRepository;
    }

    public AccountService(AccountRepository repository, PasswordEncoder passwordEncoder, MongoTemplate mongoTemplate) {
        this(repository, passwordEncoder, mongoTemplate, null, null, null);
    }

    public List<AccountDto> list() {
        return repository.findAll().stream().map(this::toDto).toList();
    }

    public org.springframework.data.domain.Page<AccountDto> list(Pageable pageable) {
        return repository.findAll(pageable).map(this::toDto);
    }

    public org.springframework.data.domain.Page<AccountDto> listByRoles(List<String> roles, Pageable pageable) {
        if (roles == null || roles.isEmpty()) {
            return list(pageable);
        }
        return repository.findByRolesIn(roles, pageable).map(this::toDto);
    }

    public org.springframework.data.domain.Page<AccountDto> search(String keyword, Boolean enabled, List<String> roles, Pageable pageable) {
        return new MongoPageQuery()
                .containsAny(keyword, "username")
                .eq("enabled", enabled)
                .in("roles", roles)
                .page(mongoTemplate, Account.class, pageable)
                .map(this::toDto);
    }

    public AccountDto create(CreateAccountRequest request) {
        if (repository.existsByUsername(request.username())) {
            throw new BusinessException("ACCOUNT_EXISTS", "账号已存在", HttpStatus.CONFLICT);
        }
        Account account = new Account();
        account.setUsername(request.username());
        account.setPasswordHash(passwordEncoder.encode(request.password()));
        account.setRoles(request.roles() == null || request.roles().isEmpty() ? List.of("OPERATOR") : request.roles());
        account.setEnabled(true);
        return toDto(repository.save(account));
    }

    public Account findEnabledByUsername(String username) {
        Account account = repository.findByUsername(username)
                .orElseThrow(() -> new BusinessException("BAD_CREDENTIALS", "用户名或密码错误", HttpStatus.UNAUTHORIZED));
        if (!account.isEnabled()) {
            throw new BusinessException("ACCOUNT_DISABLED", "账号已禁用", HttpStatus.FORBIDDEN);
        }
        return account;
    }

    public void verifyLoginDevice(Account account, String deviceId) {
        if (!account.getRoles().contains("DESKTOP_USER")) {
            return;
        }
        if (deviceId == null || deviceId.isBlank()) {
            throw new BusinessException("DEVICE_ID_REQUIRED", "桌面端登录需要设备号", HttpStatus.BAD_REQUEST);
        }
        if (account.getBoundDeviceId() == null || account.getBoundDeviceId().isBlank()) {
            account.setBoundDeviceId(deviceId);
        } else if (!account.getBoundDeviceId().equals(deviceId)) {
            throw new BusinessException("DEVICE_MISMATCH", "账号已绑定其他设备，不允许在当前设备登录", HttpStatus.FORBIDDEN);
        }
        account.setLastLoginDeviceId(deviceId);
        repository.save(account);
    }

    public void markLogin(Account account) {
        account.setLastLoginAt(Instant.now());
        repository.save(account);
    }

    public AccountDto setEnabled(String id, boolean enabled) {
        Account account = repository.findById(id)
                .orElseThrow(() -> new BusinessException("ACCOUNT_NOT_FOUND", "账号不存在", HttpStatus.NOT_FOUND));
        account.setEnabled(enabled);
        return toDto(repository.save(account));
    }

    public AccountDto resetPassword(String id, String password) {
        Account account = repository.findById(id)
                .orElseThrow(() -> new BusinessException("ACCOUNT_NOT_FOUND", "账号不存在", HttpStatus.NOT_FOUND));
        account.setPasswordHash(passwordEncoder.encode(password));
        return toDto(repository.save(account));
    }

    public AccountDto updateTodayClaimCount(String id, Integer todayClaimCount) {
        Account account = repository.findById(id)
                .orElseThrow(() -> new BusinessException("ACCOUNT_NOT_FOUND", "账号不存在", HttpStatus.NOT_FOUND));
        if (!account.getRoles().contains("DESKTOP_USER")) {
            throw new BusinessException("TODAY_CLAIM_COUNT_NOT_ALLOWED", "只有桌面端用户可以校准今日已领取数", HttpStatus.BAD_REQUEST);
        }
        if (todayClaimCount == null) {
            throw new BusinessException("TODAY_CLAIM_COUNT_REQUIRED", "请输入今日已领取数", HttpStatus.BAD_REQUEST);
        }
        if (todayClaimCount < 0) {
            throw new BusinessException("TODAY_CLAIM_COUNT_INVALID", "今日已领取数不能小于 0", HttpStatus.BAD_REQUEST);
        }
        long adjustment = (long) todayClaimCount - rawTodayClaimCount(account);
        if (adjustment < Integer.MIN_VALUE || adjustment > Integer.MAX_VALUE) {
            throw new BusinessException("TODAY_CLAIM_COUNT_INVALID", "今日已领取数超出可设置范围", HttpStatus.BAD_REQUEST);
        }
        account.setDailyClaimCountAdjustmentDate(dailyLimitDateKey());
        account.setDailyClaimCountAdjustment((int) adjustment);
        return toDto(repository.save(account));
    }

    public AccountDto bindDevice(String id, String deviceId) {
        Account account = repository.findById(id)
                .orElseThrow(() -> new BusinessException("ACCOUNT_NOT_FOUND", "账号不存在", HttpStatus.NOT_FOUND));
        if (!account.getRoles().contains("DESKTOP_USER")) {
            throw new BusinessException("DEVICE_BINDING_NOT_ALLOWED", "只有桌面端用户可以绑定设备", HttpStatus.BAD_REQUEST);
        }
        if (deviceId == null || deviceId.isBlank()) {
            throw new BusinessException("DEVICE_ID_REQUIRED", "设备号不能为空", HttpStatus.BAD_REQUEST);
        }
        account.setBoundDeviceId(deviceId.trim());
        return toDto(repository.save(account));
    }

    public AccountDto clearDeviceBinding(String id) {
        Account account = repository.findById(id)
                .orElseThrow(() -> new BusinessException("ACCOUNT_NOT_FOUND", "账号不存在", HttpStatus.NOT_FOUND));
        if (!account.getRoles().contains("DESKTOP_USER")) {
            throw new BusinessException("DEVICE_BINDING_NOT_ALLOWED", "只有桌面端用户可以绑定设备", HttpStatus.BAD_REQUEST);
        }
        account.setBoundDeviceId(null);
        return toDto(repository.save(account));
    }

    public void bootstrapAdmin(String username, String password) {
        var existing = repository.findByUsername(username);
        if (existing.isPresent()) {
            Account account = existing.get();
            account.setPasswordHash(passwordEncoder.encode(password));
            account.setRoles(List.of("ADMIN"));
            account.setEnabled(true);
            repository.save(account);
            return;
        }
        Account account = new Account();
        account.setUsername(username);
        account.setPasswordHash(passwordEncoder.encode(password));
        account.setRoles(List.of("ADMIN"));
        account.setEnabled(true);
        repository.save(account);
    }

    private AccountDto toDto(Account account) {
        return AccountDto.from(account, adjustedTodayClaimCount(account));
    }

    private long adjustedTodayClaimCount(Account account) {
        long count = rawTodayClaimCount(account) + dailyClaimCountAdjustment(account);
        return Math.max(0, count);
    }

    private long rawTodayClaimCount(Account account) {
        if (account == null || !account.getRoles().contains("DESKTOP_USER")) {
            return 0;
        }
        if (mediaAccountRepository == null || taskRepository == null) {
            return 0;
        }
        List<String> mediaAccountIds = mediaAccountRepository.findByOwnerAccountId(account.getId()).stream()
                .filter(this::requiresDailyAutomationLimit)
                .map(MediaAccount::getId)
                .filter(value -> value != null && !value.isBlank())
                .distinct()
                .toList();
        if (mediaAccountIds.isEmpty()) {
            return 0;
        }
        Instant dayStart = dailyLimitDayStart();
        return dailyClaimCount(mediaAccountIds, dayStart)
                + taskRepository.countByMediaAccountIdInAndClaimedAtIsNullAndUpdatedAtGreaterThanEqualAndStatusIn(
                        mediaAccountIds,
                        dayStart,
                        DAILY_CLAIMED_TASK_STATUSES
                );
    }

    private int dailyClaimCountAdjustment(Account account) {
        if (account == null || !dailyLimitDateKey().equals(account.getDailyClaimCountAdjustmentDate())) {
            return 0;
        }
        return account.getDailyClaimCountAdjustment();
    }

    private long dailyClaimCount(List<String> mediaAccountIds, Instant dayStart) {
        if (taskClaimRepository != null) {
            return taskClaimRepository.countByMediaAccountIdInAndClaimedAtGreaterThanEqual(mediaAccountIds, dayStart);
        }
        return taskRepository.countByMediaAccountIdInAndClaimedAtGreaterThanEqual(mediaAccountIds, dayStart);
    }

    private boolean requiresDailyAutomationLimit(MediaAccount media) {
        if (media == null) {
            return false;
        }
        return media.getPlatform() == null || media.getPlatform() == MediaPlatform.WECHAT_VIDEO;
    }

    private Instant dailyLimitDayStart() {
        return dailyLimitDateTime()
                .toLocalDate()
                .atStartOfDay(DAILY_LIMIT_ZONE)
                .toInstant();
    }

    private String dailyLimitDateKey() {
        return dailyLimitDateTime().toLocalDate().toString();
    }

    private ZonedDateTime dailyLimitDateTime() {
        return ZonedDateTime.now(DAILY_LIMIT_ZONE);
    }
}
