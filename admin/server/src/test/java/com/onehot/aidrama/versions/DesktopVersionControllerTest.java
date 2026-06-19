package com.onehot.aidrama.versions;

import com.onehot.aidrama.common.ApiResponse;
import org.junit.jupiter.api.Test;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.mock.web.MockMultipartFile;

import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class DesktopVersionControllerTest {
    @Test
    void createDelegatesToServiceAndReturnsVersionResponse() {
        DesktopVersionService service = mock(DesktopVersionService.class);
        DesktopVersionController controller = new DesktopVersionController(
                mock(DesktopVersionRepository.class),
                service,
                mock(DesktopVersionStorage.class)
        );
        DesktopVersion created = version("MAC", "0.2.0", false);
        when(service.create(any())).thenReturn(created);

        ApiResponse<VersionDtos.VersionResponse> response = controller.create(
                new VersionDtos.VersionRequest("MAC", "0.2.0", "notes", false)
        );

        assertThat(response.data().platform()).isEqualTo("MAC");
        assertThat(response.data().version()).isEqualTo("0.2.0");
    }

    @Test
    void uploadStoresPackageForVersionPlatformAndVersion() {
        DesktopVersionService service = mock(DesktopVersionService.class);
        DesktopVersionStorage storage = mock(DesktopVersionStorage.class);
        DesktopVersionController controller = new DesktopVersionController(
                mock(DesktopVersionRepository.class),
                service,
                storage
        );
        DesktopVersion existing = version("WINDOWS", "0.2.0", false);
        MockMultipartFile file = new MockMultipartFile("file", "setup.exe", "application/octet-stream", "x".getBytes());
        DesktopVersionStorage.StoredFile stored = new DesktopVersionStorage.StoredFile("setup.exe", 1, "/uploads/setup.exe");
        DesktopVersion updated = version("WINDOWS", "0.2.0", false);
        updated.setDownloadUrl("/uploads/setup.exe");
        when(service.get("version-1")).thenReturn(existing);
        when(storage.store("WINDOWS", "0.2.0", file)).thenReturn(stored);
        when(service.attachPackage("version-1", stored)).thenReturn(updated);

        ApiResponse<VersionDtos.VersionResponse> response = controller.upload("version-1", file);

        assertThat(response.data().downloadUrl()).isEqualTo("/uploads/setup.exe");
        verify(storage).store("WINDOWS", "0.2.0", file);
    }

    @Test
    void checkUpdateReturnsAvailableVersionWhenServiceFindsOne() {
        DesktopVersionService service = mock(DesktopVersionService.class);
        DesktopVersionController controller = new DesktopVersionController(
                mock(DesktopVersionRepository.class),
                service,
                mock(DesktopVersionStorage.class)
        );
        DesktopVersion update = version("MAC", "0.2.0", true);
        update.setDownloadUrl("/uploads/app.dmg");
        when(service.findUpdate("MAC", "0.1.0")).thenReturn(Optional.of(update));

        ApiResponse<VersionDtos.UpdateCheckResponse> response = controller.check("MAC", "0.1.0");

        assertThat(response.data().updateAvailable()).isTrue();
        assertThat(response.data().version()).isEqualTo("0.2.0");
    }

    @Test
    void listReturnsPagedVersionResponses() {
        DesktopVersionRepository repository = mock(DesktopVersionRepository.class);
        DesktopVersionController controller = new DesktopVersionController(
                repository,
                mock(DesktopVersionService.class),
                mock(DesktopVersionStorage.class)
        );
        when(repository.findAll(PageRequest.of(0, 20)))
                .thenReturn(new PageImpl<>(List.of(version("MAC", "0.2.0", true))));

        ApiResponse<?> response = controller.list(PageRequest.of(0, 20));

        assertThat(response.data()).isNotNull();
    }

    private static DesktopVersion version(String platform, String version, boolean published) {
        DesktopVersion item = new DesktopVersion();
        item.setPlatform(platform);
        item.setVersion(version);
        item.setPublished(published);
        item.setReleaseNotes("notes");
        return item;
    }
}
