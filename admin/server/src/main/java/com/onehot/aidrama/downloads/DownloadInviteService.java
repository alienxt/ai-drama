package com.onehot.aidrama.downloads;

import com.onehot.aidrama.common.error.BusinessException;
import com.onehot.aidrama.versions.DesktopVersion;
import com.onehot.aidrama.versions.DesktopVersionService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

import java.security.SecureRandom;
import java.time.Clock;
import java.time.Instant;
import java.util.Locale;

@Service
public class DownloadInviteService {
    private static final String CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
    private static final SecureRandom RANDOM = new SecureRandom();

    private final DownloadInviteRepository repository;
    private final DesktopVersionService versionService;
    private final Clock clock;

    @Autowired
    public DownloadInviteService(DownloadInviteRepository repository, DesktopVersionService versionService) {
        this(repository, versionService, Clock.systemUTC());
    }

    DownloadInviteService(DownloadInviteRepository repository, DesktopVersionService versionService, Clock clock) {
        this.repository = repository;
        this.versionService = versionService;
        this.clock = clock;
    }

    public DownloadInvite create(DownloadInviteDtos.InviteRequest request) {
        DownloadInvite invite = new DownloadInvite();
        invite.setCode(resolveNewCode(request.code()));
        apply(invite, request);
        return repository.save(invite);
    }

    public DownloadInvite update(String id, DownloadInviteDtos.InviteRequest request) {
        DownloadInvite invite = get(id);
        if (request.code() != null && !request.code().isBlank()) {
            String normalizedCode = normalizeCode(request.code());
            if (!normalizedCode.equals(invite.getCode()) && repository.existsByCode(normalizedCode)) {
                throw new BusinessException("DOWNLOAD_INVITE_DUPLICATED", "邀请码已存在", HttpStatus.CONFLICT);
            }
            invite.setCode(normalizedCode);
        }
        apply(invite, request);
        return repository.save(invite);
    }

    public DownloadInvite get(String id) {
        return repository.findById(id)
                .orElseThrow(() -> new BusinessException("DOWNLOAD_INVITE_NOT_FOUND", "邀请码不存在", HttpStatus.NOT_FOUND));
    }

    public DownloadInviteDtos.DownloadAccessResponse validate(String code, String platform) {
        DownloadInvite invite = repository.findByCode(normalizeCode(code))
                .orElseThrow(() -> invalidInvite("邀请码无效"));
        assertUsable(invite);
        DesktopVersion version = versionService.findLatestPublished(platform)
                .orElseThrow(() -> new BusinessException("DESKTOP_VERSION_NOT_AVAILABLE", "当前平台暂无可下载版本", HttpStatus.NOT_FOUND));
        invite.setUsedCount(invite.getUsedCount() + 1);
        invite.setLastUsedAt(Instant.now(clock));
        repository.save(invite);
        return DownloadInviteDtos.DownloadAccessResponse.from(version);
    }

    private void apply(DownloadInvite invite, DownloadInviteDtos.InviteRequest request) {
        invite.setNote(request.note());
        invite.setEnabled(request.enabled());
        invite.setMaxUses(Math.max(request.maxUses(), 0));
        invite.setExpiresAt(request.expiresAt());
    }

    private String resolveNewCode(String requestedCode) {
        if (requestedCode != null && !requestedCode.isBlank()) {
            String normalizedCode = normalizeCode(requestedCode);
            if (repository.existsByCode(normalizedCode)) {
                throw new BusinessException("DOWNLOAD_INVITE_DUPLICATED", "邀请码已存在", HttpStatus.CONFLICT);
            }
            return normalizedCode;
        }
        String generated;
        do {
            generated = generateCode();
        } while (repository.existsByCode(generated));
        return generated;
    }

    private void assertUsable(DownloadInvite invite) {
        if (!invite.isEnabled()) {
            throw invalidInvite("邀请码已停用");
        }
        Instant expiresAt = invite.getExpiresAt();
        if (expiresAt != null && !expiresAt.isAfter(Instant.now(clock))) {
            throw invalidInvite("邀请码已过期");
        }
        if (invite.getMaxUses() > 0 && invite.getUsedCount() >= invite.getMaxUses()) {
            throw invalidInvite("邀请码使用次数已用完");
        }
    }

    private BusinessException invalidInvite(String message) {
        return new BusinessException("DOWNLOAD_INVITE_INVALID", message, HttpStatus.BAD_REQUEST);
    }

    static String normalizeCode(String code) {
        if (code == null || code.isBlank()) {
            throw new BusinessException("DOWNLOAD_INVITE_REQUIRED", "请输入邀请码", HttpStatus.BAD_REQUEST);
        }
        return code.replaceAll("\\s+", "").toUpperCase(Locale.ROOT);
    }

    private static String generateCode() {
        StringBuilder builder = new StringBuilder(8);
        for (int index = 0; index < 8; index++) {
            builder.append(CODE_ALPHABET.charAt(RANDOM.nextInt(CODE_ALPHABET.length())));
        }
        return builder.toString();
    }
}
