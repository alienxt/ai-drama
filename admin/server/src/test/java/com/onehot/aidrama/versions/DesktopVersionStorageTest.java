package com.onehot.aidrama.versions;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.mock.web.MockMultipartFile;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class DesktopVersionStorageTest {
    @TempDir
    Path uploadDir;

    @Test
    void storesMacInstallerUnderPlatformAndVersionDirectory() throws Exception {
        DesktopVersionStorage storage = new DesktopVersionStorage(uploadDir);
        MockMultipartFile file = new MockMultipartFile(
                "file",
                "AI Drama 0.2.0.dmg",
                "application/octet-stream",
                "installer".getBytes()
        );

        DesktopVersionStorage.StoredFile stored = storage.store("MAC", "0.2.0", file);

        assertThat(stored.fileName()).isEqualTo("AI Drama 0.2.0.dmg");
        assertThat(stored.fileSize()).isEqualTo(9);
        assertThat(stored.downloadUrl()).isEqualTo("/uploads/desktop-versions/MAC/0.2.0/AI%20Drama%200.2.0.dmg");
        assertThat(Files.readString(uploadDir.resolve("desktop-versions/MAC/0.2.0/AI Drama 0.2.0.dmg")))
                .isEqualTo("installer");
    }

    @Test
    void rejectsUnsupportedInstallerExtensionForPlatform() {
        DesktopVersionStorage storage = new DesktopVersionStorage(uploadDir);
        MockMultipartFile file = new MockMultipartFile(
                "file",
                "AI Drama.zip",
                "application/zip",
                "installer".getBytes()
        );

        assertThatThrownBy(() -> storage.store("WINDOWS", "0.2.0", file))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("Unsupported installer file");
    }
}
