package com.onehot.aidrama.distribution;

import com.onehot.aidrama.media.MediaPlatform;

import java.time.Instant;

public class DistributionDtos {
    public record AdminTaskResponse(
            String id,
            String ownerAccountId,
            String ownerUsername,
            String mediaAccountId,
            String mediaAccountName,
            MediaPlatform platform,
            String dramaId,
            String dramaTitle,
            String dramaSource,
            String dramaProviderName,
            DistributionTaskStatus status,
            int progress,
            String failureReason,
            String platformPublishId,
            Instant createdAt,
            Instant finishedAt
    ) {
        public static AdminTaskResponse from(
                DistributionTask task,
                String ownerAccountId,
                String ownerUsername,
                String mediaAccountName,
                String dramaTitle,
                String dramaSource,
                String dramaProviderName
        ) {
            return new AdminTaskResponse(
                    task.getId(),
                    ownerAccountId,
                    ownerUsername,
                    task.getMediaAccountId(),
                    mediaAccountName,
                    task.getPlatform(),
                    task.getDramaId(),
                    dramaTitle,
                    dramaSource,
                    dramaProviderName,
                    task.getStatus(),
                    task.getProgress(),
                    task.getFailureReason(),
                    task.getPlatformPublishId(),
                    task.getCreatedAt(),
                    resolveFinishedAt(task)
            );
        }

        private static Instant resolveFinishedAt(DistributionTask task) {
            if (task.getFinishedAt() != null) {
                return task.getFinishedAt();
            }
            return switch (task.getStatus()) {
                case SUCCEEDED, FAILED, CANCELLED -> task.getUpdatedAt();
                default -> null;
            };
        }
    }

    public record TaskStatusCount(DistributionTaskStatus status, long count) {
    }

    public record ClaimRequest(String deviceId, Boolean asyncPreparation) {
        public boolean useAsyncPreparation() {
            return Boolean.TRUE.equals(asyncPreparation);
        }
    }

    public record PreparationResponse(
            boolean prepared,
            boolean preparing,
            boolean failed,
            String message,
            int retryAfterSeconds
    ) {
    }

    public record ProgressRequest(DistributionTaskStatus status, int progress, String message) {
    }

    public record ResultRequest(boolean success, String platformPublishId, String failureReason, Boolean platformSubmitted) {
    }

    public record AdminTaskStatusUpdateRequest(
            DistributionTaskStatus status,
            Integer progress,
            String failureReason,
            Boolean clearPlatformPublishMarker
    ) {
    }

    public record HeartbeatRequest(String deviceId, String appVersion, String osName, boolean idle) {
    }
}
