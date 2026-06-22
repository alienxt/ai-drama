package com.onehot.aidrama.contracts;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.util.UriUtils;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

@Component
public class ContractTemplateStorage {
    private final Path uploadDir;

    public ContractTemplateStorage(@Value("${aidrama.storage.upload-dir:uploads}") Path uploadDir) {
        this.uploadDir = uploadDir.toAbsolutePath().normalize();
    }

    public StoredFile store(ContractTemplateType type, String templateId, MultipartFile file) {
        String fileName = cleanFileName(file.getOriginalFilename());
        validateFile(fileName);
        Path targetDir = uploadDir.resolve("contract-templates").resolve(type.name()).resolve(templateId).normalize();
        if (!targetDir.startsWith(uploadDir)) {
            throw new IllegalArgumentException("Invalid contract template path");
        }
        try {
            Files.createDirectories(targetDir);
            clearExistingFiles(targetDir);
            Path target = targetDir.resolve(fileName);
            file.transferTo(target);
            String encodedFileName = UriUtils.encodePathSegment(fileName, StandardCharsets.UTF_8);
            String downloadUrl = "/uploads/contract-templates/" + type.name() + "/" + templateId + "/" + encodedFileName;
            return new StoredFile(fileName, Files.size(target), downloadUrl);
        } catch (IOException exception) {
            throw new IllegalStateException("Failed to store contract template file", exception);
        }
    }

    private static void clearExistingFiles(Path targetDir) throws IOException {
        try (var paths = Files.list(targetDir)) {
            for (Path path : paths.toList()) {
                if (Files.isRegularFile(path)) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }

    private static String cleanFileName(String original) {
        String fileName = Path.of(original == null ? "" : original).getFileName().toString().trim();
        if (fileName.isBlank()) {
            throw new IllegalArgumentException("Contract template file name is required");
        }
        return fileName;
    }

    private static void validateFile(String fileName) {
        if (!fileName.toLowerCase(Locale.ROOT).endsWith(".docx")) {
            throw new IllegalArgumentException("合同模板仅支持 .docx 文件");
        }
    }

    public record StoredFile(String fileName, long fileSize, String downloadUrl) {
    }
}
