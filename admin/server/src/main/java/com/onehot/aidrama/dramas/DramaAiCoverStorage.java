package com.onehot.aidrama.dramas;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Base64;
import java.util.Locale;
import java.util.UUID;

@Component
public class DramaAiCoverStorage {
    private final Path uploadDir;

    public DramaAiCoverStorage(@Value("${aidrama.storage.upload-dir:uploads}") Path uploadDir) {
        this.uploadDir = uploadDir.toAbsolutePath().normalize();
    }

    public String store(String base64Image, String outputFormat) {
        String extension = extension(outputFormat);
        String fileName = UUID.randomUUID().toString().replace("-", "") + extension;
        Path target = uploadDir.resolve("ai-covers").resolve(fileName);
        try {
            Files.createDirectories(target.getParent());
            Files.write(target, Base64.getDecoder().decode(base64Image));
        } catch (IllegalArgumentException | IOException exception) {
            throw new IllegalStateException("保存 AI 封面失败", exception);
        }
        return "/uploads/ai-covers/" + fileName;
    }

    private String extension(String outputFormat) {
        return switch ((outputFormat == null ? "" : outputFormat).toLowerCase(Locale.ROOT)) {
            case "png" -> ".png";
            case "webp" -> ".webp";
            default -> ".jpg";
        };
    }
}
