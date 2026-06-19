package com.onehot.aidrama.downloads;

import com.onehot.aidrama.common.error.BusinessException;
import com.onehot.aidrama.versions.DesktopVersion;
import com.onehot.aidrama.versions.DesktopVersionService;
import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class DownloadInviteServiceTest {
    private static final Instant NOW = Instant.parse("2026-06-20T10:00:00Z");
    private final DownloadInviteRepository repository = mock(DownloadInviteRepository.class);
    private final DesktopVersionService versionService = mock(DesktopVersionService.class);
    private final DownloadInviteService service = new DownloadInviteService(
            repository,
            versionService,
            Clock.fixed(NOW, ZoneOffset.UTC)
    );

    @Test
    void validateReturnsDownloadUrlAndConsumesInvite() {
        DownloadInvite invite = invite("DRAMA2026");
        DesktopVersion version = version("MAC");
        when(repository.findByCode("DRAMA2026")).thenReturn(Optional.of(invite));
        when(versionService.findLatestPublished("MAC")).thenReturn(Optional.of(version));

        DownloadInviteDtos.DownloadAccessResponse response = service.validate(" drama 2026 ", "MAC");

        assertThat(response.valid()).isTrue();
        assertThat(response.downloadUrl()).isEqualTo("/uploads/app.dmg");
        assertThat(invite.getUsedCount()).isEqualTo(1);
        assertThat(invite.getLastUsedAt()).isEqualTo(NOW);
        verify(repository).save(invite);
    }

    @Test
    void validateRejectsExhaustedInvite() {
        DownloadInvite invite = invite("USEDUP");
        invite.setMaxUses(1);
        invite.setUsedCount(1);
        when(repository.findByCode("USEDUP")).thenReturn(Optional.of(invite));

        assertThatThrownBy(() -> service.validate("USEDUP", "MAC"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("使用次数");
    }

    @Test
    void validateRejectsExpiredInvite() {
        DownloadInvite invite = invite("EXPIRED");
        invite.setExpiresAt(NOW.minusSeconds(1));
        when(repository.findByCode("EXPIRED")).thenReturn(Optional.of(invite));

        assertThatThrownBy(() -> service.validate("EXPIRED", "MAC"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("过期");
    }

    @Test
    void createsUppercaseGeneratedCodeWhenCodeIsProvided() {
        DownloadInvite saved = invite("HELLO");
        when(repository.save(org.mockito.ArgumentMatchers.any(DownloadInvite.class))).thenReturn(saved);

        DownloadInvite created = service.create(new DownloadInviteDtos.InviteRequest(
                " hello ",
                "测试",
                true,
                3,
                null
        ));

        assertThat(created.getCode()).isEqualTo("HELLO");
    }

    private static DownloadInvite invite(String code) {
        DownloadInvite invite = new DownloadInvite();
        invite.setCode(code);
        invite.setEnabled(true);
        invite.setExpiresAt(NOW.plusSeconds(3600));
        return invite;
    }

    private static DesktopVersion version(String platform) {
        DesktopVersion version = new DesktopVersion();
        version.setPlatform(platform);
        version.setVersion("0.2.0");
        version.setFileName("AI Drama.dmg");
        version.setFileSize(1024);
        version.setDownloadUrl("/uploads/app.dmg");
        version.setPublished(true);
        return version;
    }
}
