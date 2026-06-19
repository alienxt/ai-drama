package com.onehot.aidrama.users;

import com.onehot.aidrama.common.MongoPageQuery;
import com.onehot.aidrama.common.error.BusinessException;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.List;

@Service
public class AccountService {
    private final AccountRepository repository;
    private final PasswordEncoder passwordEncoder;
    private final MongoTemplate mongoTemplate;

    public AccountService(AccountRepository repository, PasswordEncoder passwordEncoder, MongoTemplate mongoTemplate) {
        this.repository = repository;
        this.passwordEncoder = passwordEncoder;
        this.mongoTemplate = mongoTemplate;
    }

    public List<AccountDto> list() {
        return repository.findAll().stream().map(AccountDto::from).toList();
    }

    public org.springframework.data.domain.Page<AccountDto> list(Pageable pageable) {
        return repository.findAll(pageable).map(AccountDto::from);
    }

    public org.springframework.data.domain.Page<AccountDto> listByRoles(List<String> roles, Pageable pageable) {
        if (roles == null || roles.isEmpty()) {
            return list(pageable);
        }
        return repository.findByRolesIn(roles, pageable).map(AccountDto::from);
    }

    public org.springframework.data.domain.Page<AccountDto> search(String keyword, Boolean enabled, List<String> roles, Pageable pageable) {
        return new MongoPageQuery()
                .containsAny(keyword, "username")
                .eq("enabled", enabled)
                .in("roles", roles)
                .page(mongoTemplate, Account.class, pageable)
                .map(AccountDto::from);
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
        return AccountDto.from(repository.save(account));
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
        return AccountDto.from(repository.save(account));
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
        return AccountDto.from(repository.save(account));
    }

    public AccountDto clearDeviceBinding(String id) {
        Account account = repository.findById(id)
                .orElseThrow(() -> new BusinessException("ACCOUNT_NOT_FOUND", "账号不存在", HttpStatus.NOT_FOUND));
        if (!account.getRoles().contains("DESKTOP_USER")) {
            throw new BusinessException("DEVICE_BINDING_NOT_ALLOWED", "只有桌面端用户可以绑定设备", HttpStatus.BAD_REQUEST);
        }
        account.setBoundDeviceId(null);
        return AccountDto.from(repository.save(account));
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
}
