package com.onehot.aidrama.hongguo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.util.HexFormat;
import java.util.Locale;

@Component
public class LocalHongguoCoverStorage implements HongguoCoverStorage {
    private static final Logger LOGGER = LoggerFactory.getLogger(LocalHongguoCoverStorage.class);
    private static final int MAX_COVER_BYTES = 10 * 1024 * 1024;

    private final Path uploadDir;
    private final HttpClient httpClient;

    @Autowired
    public LocalHongguoCoverStorage(@Value("${aidrama.storage.upload-dir:uploads}") Path uploadDir) {
        this(uploadDir, HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .followRedirects(HttpClient.Redirect.NORMAL)
                .build());
    }

    LocalHongguoCoverStorage(Path uploadDir, HttpClient httpClient) {
        this.uploadDir = uploadDir.toAbsolutePath().normalize();
        this.httpClient = httpClient;
    }

    @Override
    public String store(String coverUrl) {
        if (coverUrl == null || coverUrl.isBlank() || coverUrl.startsWith("/uploads/")) {
            return coverUrl;
        }
        URI uri;
        try {
            uri = URI.create(coverUrl.trim());
        } catch (IllegalArgumentException exception) {
            return coverUrl;
        }
        if (!"http".equalsIgnoreCase(uri.getScheme()) && !"https".equalsIgnoreCase(uri.getScheme())) {
            return coverUrl;
        }

        String hash = sha256(uri.toString());
        String fileName = hash + extension(uri.getPath());
        Path target = uploadDir.resolve("covers").resolve(fileName);
        if (hasExistingFile(target)) {
            return "/uploads/covers/" + fileName;
        }

        try {
            byte[] bytes = download(uri);
            if (isHeif(bytes)) {
                fileName = hash + ".jpg";
                target = uploadDir.resolve("covers").resolve(fileName);
                if (hasExistingFile(target)) {
                    return "/uploads/covers/" + fileName;
                }
            }
            Files.createDirectories(target.getParent());
            Path temp = target.resolveSibling(target.getFileName() + ".tmp");
            if (isHeif(bytes)) {
                writeHeifAsJpeg(bytes, temp);
            } else {
                Files.write(temp, bytes);
            }
            moveIntoPlace(temp, target);
            return "/uploads/covers/" + fileName;
        } catch (Exception exception) {
            LOGGER.warn("Hongguo cover download failed: url={}, reason={}", coverUrl, exception.getMessage());
            return coverUrl;
        }
    }

    private void moveIntoPlace(Path temp, Path target) throws IOException {
        try {
            Files.move(temp, target, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        } catch (AtomicMoveNotSupportedException exception) {
            Files.move(temp, target, StandardCopyOption.REPLACE_EXISTING);
        }
    }

    private byte[] download(URI uri) throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(30))
                .header("User-Agent", "ai-drama-server/1.0")
                .GET()
                .build();
        HttpResponse<byte[]> response = httpClient.send(request, HttpResponse.BodyHandlers.ofByteArray());
        int status = response.statusCode();
        if (status < 200 || status >= 300) {
            throw new IOException("HTTP " + status);
        }
        byte[] body = response.body();
        if (body == null || body.length == 0) {
            throw new IOException("empty response");
        }
        if (body.length > MAX_COVER_BYTES) {
            throw new IOException("cover is too large");
        }
        return body;
    }

    private void writeHeifAsJpeg(byte[] bytes, Path output) throws IOException, InterruptedException {
        Path input = output.resolveSibling(output.getFileName() + ".heif");
        Files.write(input, bytes);
        try {
            Process process = new ProcessBuilder(
                    "ffmpeg",
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    input.toString(),
                    "-frames:v",
                    "1",
                    "-q:v",
                    "2",
                    output.toString()
            ).start();
            int exitCode = process.waitFor();
            if (exitCode != 0 || !hasExistingFile(output)) {
                throw new IOException("ffmpeg HEIF conversion failed with exit code " + exitCode);
            }
        } finally {
            Files.deleteIfExists(input);
        }
    }

    private boolean isHeif(byte[] bytes) {
        if (bytes == null || bytes.length < 12) {
            return false;
        }
        String header = new String(bytes, 4, Math.min(bytes.length - 4, 64), StandardCharsets.ISO_8859_1);
        return header.contains("ftypheic")
                || header.contains("ftypheix")
                || header.contains("ftyphevc")
                || header.contains("ftyphevx")
                || header.contains("ftypmif1")
                || header.contains("ftypmsf1");
    }

    private boolean hasExistingFile(Path target) {
        try {
            return Files.isRegularFile(target) && Files.size(target) > 0;
        } catch (IOException exception) {
            return false;
        }
    }

    private String extension(String path) {
        if (path == null) {
            return ".jpg";
        }
        int slash = path.lastIndexOf('/');
        String name = slash >= 0 ? path.substring(slash + 1) : path;
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
