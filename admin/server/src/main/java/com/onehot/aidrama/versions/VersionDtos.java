package com.onehot.aidrama.versions;

import java.time.Instant;

public class VersionDtos {
    public record VersionRequest(
            String platform,
            String version,
            String releaseNotes,
            boolean mandatory
    ) {
    }

    public record PublishRequest(boolean published) {
    }

    public record VersionResponse(
            String id,
            String platform,
            String version,
            String releaseNotes,
            boolean mandatory,
            boolean published,
            String fileName,
            long fileSize,
            String downloadUrl,
            Instant createdAt,
            Instant updatedAt
    ) {
        public static VersionResponse from(DesktopVersion version) {
            return new VersionResponse(
                    version.getId(),
                    version.getPlatform(),
                    version.getVersion(),
                    version.getReleaseNotes(),
                    version.isMandatory(),
                    version.isPublished(),
                    version.getFileName(),
                    version.getFileSize(),
                    version.getDownloadUrl(),
                    version.getCreatedAt(),
                    version.getUpdatedAt()
            );
        }
    }

    public record UpdateCheckResponse(
            boolean updateAvailable,
            String platform,
            String version,
            String releaseNotes,
            boolean mandatory,
            String fileName,
            long fileSize,
            String downloadUrl
    ) {
        public static UpdateCheckResponse none() {
            return new UpdateCheckResponse(false, null, null, null, false, null, 0, null);
        }

        public static UpdateCheckResponse available(DesktopVersion version) {
            return new UpdateCheckResponse(
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
