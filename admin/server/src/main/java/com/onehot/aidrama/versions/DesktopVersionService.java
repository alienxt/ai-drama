package com.onehot.aidrama.versions;

import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import com.onehot.aidrama.common.error.BusinessException;

import java.util.Comparator;
import java.util.Optional;

@Service
public class DesktopVersionService {
    private final DesktopVersionRepository repository;

    public DesktopVersionService(DesktopVersionRepository repository) {
        this.repository = repository;
    }

    public Optional<DesktopVersion> findUpdate(String platform, String currentVersion) {
        String normalizedPlatform = normalizePlatform(platform);
        return findLatestPublished(normalizedPlatform)
                .filter(version -> compareVersions(version.getVersion(), currentVersion) > 0);
    }

    public Optional<DesktopVersion> findLatestPublished(String platform) {
        String normalizedPlatform = normalizePlatform(platform);
        return repository.findByPlatformAndPublished(
                normalizedPlatform,
                true,
                Sort.by(Sort.Direction.DESC, "createdAt")
        )
                .stream()
                .filter(version -> normalizedPlatform.equals(version.getPlatform()))
                .filter(DesktopVersion::isPublished)
                .filter(version -> version.getDownloadUrl() != null && !version.getDownloadUrl().isBlank())
                .max(Comparator.comparing(DesktopVersion::getVersion, DesktopVersionService::compareVersions));
    }

    public DesktopVersion create(VersionDtos.VersionRequest request) {
        DesktopVersion version = new DesktopVersion();
        version.setPlatform(normalizePlatform(request.platform()));
        version.setVersion(request.version());
        version.setReleaseNotes(request.releaseNotes());
        version.setMandatory(request.mandatory());
        version.setPublished(false);
        return repository.save(version);
    }

    public DesktopVersion attachPackage(String id, DesktopVersionStorage.StoredFile file) {
        DesktopVersion version = get(id);
        version.setFileName(file.fileName());
        version.setFileSize(file.fileSize());
        version.setDownloadUrl(file.downloadUrl());
        return repository.save(version);
    }

    public DesktopVersion setPublished(String id, boolean published) {
        DesktopVersion version = get(id);
        if (published && (version.getDownloadUrl() == null || version.getDownloadUrl().isBlank())) {
            throw new IllegalStateException("Cannot publish desktop version before package upload");
        }
        version.setPublished(published);
        return repository.save(version);
    }

    public DesktopVersion get(String id) {
        return repository.findById(id)
                .orElseThrow(() -> new BusinessException("DESKTOP_VERSION_NOT_FOUND", "桌面版本不存在", HttpStatus.NOT_FOUND));
    }

    public String normalizePlatform(String platform) {
        if (platform == null || platform.isBlank()) {
            throw new IllegalArgumentException("Unsupported desktop platform: " + platform);
        }
        try {
            return DesktopPlatform.valueOf(platform.trim().toUpperCase()).name();
        } catch (IllegalArgumentException exception) {
            throw new IllegalArgumentException("Unsupported desktop platform: " + platform, exception);
        }
    }

    static int compareVersions(String left, String right) {
        int[] leftParts = versionParts(left);
        int[] rightParts = versionParts(right);
        int length = Math.max(leftParts.length, rightParts.length);
        for (int index = 0; index < length; index++) {
            int leftValue = index < leftParts.length ? leftParts[index] : 0;
            int rightValue = index < rightParts.length ? rightParts[index] : 0;
            if (leftValue != rightValue) {
                return Integer.compare(leftValue, rightValue);
            }
        }
        return 0;
    }

    private static int[] versionParts(String version) {
        if (version == null || version.isBlank()) {
            return new int[] {0};
        }
        String normalized = version.trim().split("-", 2)[0];
        String[] parts = normalized.split("\\.");
        int[] numbers = new int[parts.length];
        for (int index = 0; index < parts.length; index++) {
            numbers[index] = parsePart(parts[index]);
        }
        return numbers;
    }

    private static int parsePart(String value) {
        try {
            return Integer.parseInt(value.replaceAll("[^0-9].*$", ""));
        } catch (NumberFormatException exception) {
            return 0;
        }
    }
}
