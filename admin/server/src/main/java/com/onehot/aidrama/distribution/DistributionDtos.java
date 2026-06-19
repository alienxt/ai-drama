package com.onehot.aidrama.distribution;

public class DistributionDtos {
    public record AdminTaskResponse(
            String id,
            String mediaAccountId,
            String mediaAccountName,
            String dramaId,
            String dramaTitle,
            DistributionTaskStatus status,
            int progress,
            String failureReason,
            String platformPublishId
    ) {
        public static AdminTaskResponse from(DistributionTask task, String mediaAccountName, String dramaTitle) {
            return new AdminTaskResponse(
                    task.getId(),
                    task.getMediaAccountId(),
                    mediaAccountName,
                    task.getDramaId(),
                    dramaTitle,
                    task.getStatus(),
                    task.getProgress(),
                    task.getFailureReason(),
                    task.getPlatformPublishId()
            );
        }
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
