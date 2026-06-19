package com.onehot.aidrama.versions;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.util.UriUtils;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.Set;

@Component
public class DesktopVersionStorage {
    private static final Set<String> MAC_EXTENSIONS = Set.of(".dmg", ".pkg");
    private static final Set<String> WINDOWS_EXTENSIONS = Set.of(".exe", ".msi");

    private final Path uploadDir;

    public DesktopVersionStorage(@Value("${aidrama.storage.upload-dir:uploads}") Path uploadDir) {
        this.uploadDir = uploadDir.toAbsolutePath().normalize();
    }

    public StoredFile store(String platform, String version, MultipartFile file) {
        String fileName = cleanFileName(file.getOriginalFilename());
        validateExtension(platform, fileName);
        Path targetDir = uploadDir.resolve("desktop-versions").resolve(platform).resolve(version).normalize();
        if (!targetDir.startsWith(uploadDir)) {
            throw new IllegalArgumentException("Invalid installer path");
        }
        try {
            Files.createDirectories(targetDir);
            Path target = targetDir.resolve(fileName);
            file.transferTo(target);
            String encodedFileName = UriUtils.encodePathSegment(fileName, StandardCharsets.UTF_8);
            String downloadUrl = "/uploads/desktop-versions/" + platform + "/" + version + "/" + encodedFileName;
            return new StoredFile(fileName, Files.size(target), downloadUrl);
        } catch (IOException exception) {
            throw new IllegalStateException("Failed to store installer file", exception);
        }
    }

    private static String cleanFileName(String original) {
        String fileName = Path.of(original == null ? "" : original).getFileName().toString().trim();
        if (fileName.isBlank()) {
            throw new IllegalArgumentException("Installer file name is required");
        }
        return fileName;
    }

    private static void validateExtension(String platform, String fileName) {
        String lower = fileName.toLowerCase(Locale.ROOT);
        Set<String> allowed = switch (DesktopPlatform.valueOf(platform)) {
            case MAC -> MAC_EXTENSIONS;
            case WINDOWS -> WINDOWS_EXTENSIONS;
        };
        if (allowed.stream().noneMatch(lower::endsWith)) {
            throw new IllegalArgumentException("Unsupported installer file for " + platform);
        }
    }

    public record StoredFile(String fileName, long fileSize, String downloadUrl) {
    }
}
