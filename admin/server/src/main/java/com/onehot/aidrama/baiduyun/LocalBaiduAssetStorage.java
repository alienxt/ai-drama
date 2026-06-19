package com.onehot.aidrama.baiduyun;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Locale;

@Component
public class LocalBaiduAssetStorage implements BaiduAssetStorage {
    private final Path uploadDir;

    public LocalBaiduAssetStorage(@Value("${aidrama.storage.upload-dir:uploads}") Path uploadDir) {
        this.uploadDir = uploadDir.toAbsolutePath().normalize();
    }

    @Override
    public String storeCover(String remotePath, BaiduPanClient baiduPanClient) {
        String fileName = sha256(remotePath) + extension(remotePath);
        Path target = uploadDir.resolve("covers").resolve(fileName);
        if (Files.isRegularFile(target)) {
            try {
                if (Files.size(target) > 0) {
                    return "/uploads/covers/" + fileName;
                }
            } catch (java.io.IOException ignored) {
                // Fall through and attempt a fresh download.
            }
        }
        baiduPanClient.downloadFile(remotePath, target);
        return "/uploads/covers/" + fileName;
    }

    @Override
    public String storeCoverBytes(String remotePath, byte[] bytes) {
        if (bytes == null || bytes.length == 0) {
            throw new BaiduPanException("Cover file is empty");
        }
        String fileName = sha256(remotePath) + extension(remotePath);
        Path target = uploadDir.resolve("covers").resolve(fileName);
        try {
            Files.createDirectories(target.getParent());
            Path temp = target.resolveSibling(target.getFileName() + ".tmp");
            Files.write(temp, bytes);
            Files.move(temp, target, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
            return "/uploads/covers/" + fileName;
        } catch (java.io.IOException exception) {
            throw new BaiduPanException("Cover file save failed", exception);
        }
    }

    private String extension(String remotePath) {
        int slash = remotePath.lastIndexOf('/');
        String name = slash >= 0 ? remotePath.substring(slash + 1) : remotePath;
        int dot = name.lastIndexOf('.');
        if (dot < 0) {
            return ".jpg";
        }
        String extension = name.substring(dot).toLowerCase(Locale.ROOT);
        return switch (extension) {
            case ".jpg", ".jpeg", ".png", ".webp" -> extension;
            default -> ".jpg";
        };
    }

    private String sha256(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(value.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(hash).substring(0, 32);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is unavailable", exception);
        }
    }
}
