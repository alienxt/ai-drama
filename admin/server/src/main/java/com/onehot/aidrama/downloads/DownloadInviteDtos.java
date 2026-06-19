package com.onehot.aidrama.downloads;

import com.onehot.aidrama.versions.DesktopVersion;

import java.time.Instant;

public class DownloadInviteDtos {
    public record InviteRequest(
            String code,
            String note,
            boolean enabled,
            int maxUses,
            Instant expiresAt
    ) {
    }

    public record ValidateRequest(String code, String platform) {
    }

    public record InviteResponse(
            String id,
            String code,
            String note,
            boolean enabled,
            int maxUses,
            int usedCount,
            Instant expiresAt,
            Instant lastUsedAt,
            Instant createdAt,
            Instant updatedAt
    ) {
        public static InviteResponse from(DownloadInvite invite) {
            return new InviteResponse(
                    invite.getId(),
                    invite.getCode(),
                    invite.getNote(),
                    invite.isEnabled(),
                    invite.getMaxUses(),
                    invite.getUsedCount(),
                    invite.getExpiresAt(),
                    invite.getLastUsedAt(),
                    invite.getCreatedAt(),
                    invite.getUpdatedAt()
            );
        }
    }

    public record PublicVersionResponse(
            boolean available,
            String platform,
            String version,
            String releaseNotes,
            boolean mandatory,
            String fileName,
            long fileSize
    ) {
        public static PublicVersionResponse none(String platform) {
            return new PublicVersionResponse(false, platform, null, null, false, null, 0);
        }

        public static PublicVersionResponse from(DesktopVersion version) {
            return new PublicVersionResponse(
                    true,
                    version.getPlatform(),
                    version.getVersion(),
                    version.getReleaseNotes(),
                    version.isMandatory(),
                    version.getFileName(),
                    version.getFileSize()
            );
        }
    }

    public record DownloadAccessResponse(
            boolean valid,
            String platform,
            String version,
            String releaseNotes,
            boolean mandatory,
            String fileName,
            long fileSize,
            String downloadUrl
    ) {
        public static DownloadAccessResponse from(DesktopVersion version) {
            return new DownloadAccessResponse(
                    true,
                    version.getPlatform(),
                    version.getVersion(),
                    version.getReleaseNotes(),
                    version.isMandatory(),
                    version.getFileName(),
                    version.getFileSize(),
                    version.getDownloadUrl()
            );
        }
    }
}
