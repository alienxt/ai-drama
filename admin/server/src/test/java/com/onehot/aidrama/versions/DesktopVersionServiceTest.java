package com.onehot.aidrama.versions;

import org.junit.jupiter.api.Test;
import org.springframework.data.domain.Sort;

import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class DesktopVersionServiceTest {
    @Test
    void checkUpdateReturnsNewestPublishedVersionForPlatformWhenCurrentIsOlder() {
        DesktopVersionRepository repository = mock(DesktopVersionRepository.class);
        DesktopVersionService service = new DesktopVersionService(repository);
        DesktopVersion oldVersion = version("MAC", "0.1.1", true);
        DesktopVersion newest = version("MAC", "0.2.0", true);
        DesktopVersion draft = version("MAC", "0.3.0", false);
        DesktopVersion windows = version("WINDOWS", "9.0.0", true);
        oldVersion.setDownloadUrl("/uploads/old.dmg");
        newest.setDownloadUrl("/uploads/new.dmg");
        windows.setDownloadUrl("/uploads/app.exe");

        when(repository.findByPlatformAndPublished("MAC", true, Sort.by(Sort.Direction.DESC, "createdAt")))
                .thenReturn(List.of(windows, draft, oldVersion, newest));

        Optional<DesktopVersion> update = service.findUpdate("MAC", "0.1.0");

        assertThat(update).contains(newest);
    }

    @Test
    void checkUpdateReturnsEmptyWhenCurrentVersionIsCurrent() {
        DesktopVersionRepository repository = mock(DesktopVersionRepository.class);
        DesktopVersionService service = new DesktopVersionService(repository);

        DesktopVersion current = version("WINDOWS", "1.2.0", true);
        current.setDownloadUrl("/uploads/app.exe");
        when(repository.findByPlatformAndPublished("WINDOWS", true, Sort.by(Sort.Direction.DESC, "createdAt")))
                .thenReturn(List.of(current));

        Optional<DesktopVersion> update = service.findUpdate("WINDOWS", "1.2.0");

        assertThat(update).isEmpty();
    }

    @Test
    void latestPublishedRequiresUploadedPackage() {
        DesktopVersionRepository repository = mock(DesktopVersionRepository.class);
        DesktopVersionService service = new DesktopVersionService(repository);
        DesktopVersion withoutPackage = version("MAC", "0.3.0", true);
        DesktopVersion withPackage = version("MAC", "0.2.0", true);
        withPackage.setDownloadUrl("/uploads/app.dmg");

        when(repository.findByPlatformAndPublished("MAC", true, Sort.by(Sort.Direction.DESC, "createdAt")))
                .thenReturn(List.of(withoutPackage, withPackage));

        Optional<DesktopVersion> latest = service.findLatestPublished("MAC");

        assertThat(latest).contains(withPackage);
    }

    @Test
    void unsupportedPlatformIsRejected() {
        DesktopVersionService service = new DesktopVersionService(mock(DesktopVersionRepository.class));

        assertThatThrownBy(() -> service.normalizePlatform("linux"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("Unsupported desktop platform");
    }

    @Test
    void createsVersionMetadataWithNormalizedPlatform() {
        DesktopVersionRepository repository = mock(DesktopVersionRepository.class);
        DesktopVersionService service = new DesktopVersionService(repository);
        when(repository.save(any(DesktopVersion.class))).thenAnswer(invocation -> invocation.getArgument(0));

        DesktopVersion created = service.create(new VersionDtos.VersionRequest(
                "mac",
                "0.2.0",
                "更新说明",
                true
        ));

        assertThat(created.getPlatform()).isEqualTo("MAC");
        assertThat(created.getVersion()).isEqualTo("0.2.0");
        assertThat(created.getReleaseNotes()).isEqualTo("更新说明");
        assertThat(created.isMandatory()).isTrue();
        assertThat(created.isPublished()).isFalse();
    }

    @Test
    void attachesStoredInstallerToExistingVersion() {
        DesktopVersionRepository repository = mock(DesktopVersionRepository.class);
        DesktopVersionService service = new DesktopVersionService(repository);
        DesktopVersion version = version("WINDOWS", "0.2.0", false);
        when(repository.findById("version-1")).thenReturn(Optional.of(version));
        when(repository.save(any(DesktopVersion.class))).thenAnswer(invocation -> invocation.getArgument(0));

        DesktopVersion updated = service.attachPackage(
                "version-1",
                new DesktopVersionStorage.StoredFile("installer.exe", 42, "/uploads/installer.exe")
        );

        assertThat(updated.getFileName()).isEqualTo("installer.exe");
        assertThat(updated.getFileSize()).isEqualTo(42);
        assertThat(updated.getDownloadUrl()).isEqualTo("/uploads/installer.exe");
        verify(repository).save(version);
    }

    @Test
    void publishRequiresPackage() {
        DesktopVersionRepository repository = mock(DesktopVersionRepository.class);
        DesktopVersionService service = new DesktopVersionService(repository);
        when(repository.findById("version-1")).thenReturn(Optional.of(version("MAC", "0.2.0", false)));

        assertThatThrownBy(() -> service.setPublished("version-1", true))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("package");
    }

    @Test
    void checkResponseIncludesUpdateMetadata() {
        DesktopVersion version = version("MAC", "0.2.0", true);
        version.setMandatory(true);
        version.setReleaseNotes("更新说明");
        version.setFileName("installer.dmg");
        version.setFileSize(100);
        version.setDownloadUrl("/uploads/installer.dmg");

        VersionDtos.UpdateCheckResponse response = VersionDtos.UpdateCheckResponse.available(version);

        assertThat(response.updateAvailable()).isTrue();
        assertThat(response.version()).isEqualTo("0.2.0");
        assertThat(response.downloadUrl()).isEqualTo("/uploads/installer.dmg");
        assertThat(response.mandatory()).isTrue();
    }

    private static DesktopVersion version(String platform, String version, boolean published) {
        DesktopVersion item = new DesktopVersion();
        item.setPlatform(platform);
        item.setVersion(version);
        item.setPublished(published);
        return item;
    }
}
