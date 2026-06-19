package com.onehot.aidrama.ai;

import java.time.Instant;
import java.util.Map;

public class AiTaskDtos {
    public record AdminAiTaskResponse(
            String id,
            AiTaskType type,
            AiTaskStatus status,
            String provider,
            String model,
            String endpoint,
            String subjectType,
            String subjectId,
            String subjectTitle,
            String prompt,
            Map<String, Object> requestPayload,
            Map<String, Object> responsePayload,
            String errorMessage,
            Long durationMs,
            Instant startedAt,
            Instant finishedAt,
            Instant createdAt,
            Instant updatedAt
    ) {
        public static AdminAiTaskResponse from(AiTask task, String subjectTitle) {
            return new AdminAiTaskResponse(
                    task.getId(),
                    task.getType(),
                    task.getStatus(),
                    task.getProvider(),
                    task.getModel(),
                    task.getEndpoint(),
                    task.getSubjectType(),
                    task.getSubjectId(),
                    subjectTitle,
                    task.getPrompt(),
                    task.getRequestPayload(),
                    task.getResponsePayload(),
                    task.getErrorMessage(),
                    task.getDurationMs(),
                    task.getStartedAt(),
                    task.getFinishedAt(),
                    task.getCreatedAt(),
                    task.getUpdatedAt()
            );
        }
    }
}
