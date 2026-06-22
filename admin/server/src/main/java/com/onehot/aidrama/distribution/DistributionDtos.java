package com.onehot.aidrama.distribution;

import java.time.Instant;

public class DistributionDtos {
    public record AdminTaskResponse(
            String id,
            String ownerAccountId,
            String ownerUsername,
            String mediaAccountId,
            String mediaAccountName,
            String dramaId,
            String dramaTitle,
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
                String dramaTitle
        ) {
            return new AdminTaskResponse(
                    task.getId(),
                    ownerAccountId,
                    ownerUsername,
                    task.getMediaAccountId(),
                    mediaAccountName,
                    task.getDramaId(),
                    dramaTitle,
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

    public record ClaimRequest(String deviceId) {
    }

    public record ProgressRequest(DistributionTaskStatus status, int progress, String message) {
    }

    public record ResultRequest(boolean success, String platformPublishId, String failureReason) {
    }

    public record HeartbeatRequest(String deviceId, String appVersion, String osName, boolean idle) {
    }
}
