package com.onehot.aidrama.ai;

import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.mongodb.core.mapping.Document;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

@Document("ai_tasks")
public class AiTask {
    @Id
    private String id;
    private AiTaskType type;
    private AiTaskStatus status = AiTaskStatus.RUNNING;
    private String provider = "OpenAI";
    private String model;
    private String endpoint;
    private String subjectType;
    private String subjectId;
    private String prompt;
    private Map<String, Object> requestPayload = new LinkedHashMap<>();
    private Map<String, Object> responsePayload = new LinkedHashMap<>();
    private String errorMessage;
    private Long durationMs;
    private Instant startedAt;
    private Instant finishedAt;
    @CreatedDate
    private Instant createdAt;
    @LastModifiedDate
    private Instant updatedAt;

    public String getId() { return id; }
    public AiTaskType getType() { return type; }
    public void setType(AiTaskType type) { this.type = type; }
    public AiTaskStatus getStatus() { return status; }
    public void setStatus(AiTaskStatus status) { this.status = status; }
    public String getProvider() { return provider; }
    public void setProvider(String provider) { this.provider = provider; }
    public String getModel() { return model; }
    public void setModel(String model) { this.model = model; }
    public String getEndpoint() { return endpoint; }
    public void setEndpoint(String endpoint) { this.endpoint = endpoint; }
    public String getSubjectType() { return subjectType; }
    public void setSubjectType(String subjectType) { this.subjectType = subjectType; }
    public String getSubjectId() { return subjectId; }
    public void setSubjectId(String subjectId) { this.subjectId = subjectId; }
    public String getPrompt() { return prompt; }
    public void setPrompt(String prompt) { this.prompt = prompt; }
    public Map<String, Object> getRequestPayload() { return requestPayload; }
    public void setRequestPayload(Map<String, Object> requestPayload) { this.requestPayload = requestPayload; }
    public Map<String, Object> getResponsePayload() { return responsePayload; }
    public void setResponsePayload(Map<String, Object> responsePayload) { this.responsePayload = responsePayload; }
    public String getErrorMessage() { return errorMessage; }
    public void setErrorMessage(String errorMessage) { this.errorMessage = errorMessage; }
    public Long getDurationMs() { return durationMs; }
    public void setDurationMs(Long durationMs) { this.durationMs = durationMs; }
    public Instant getStartedAt() { return startedAt; }
    public void setStartedAt(Instant startedAt) { this.startedAt = startedAt; }
    public Instant getFinishedAt() { return finishedAt; }
    public void setFinishedAt(Instant finishedAt) { this.finishedAt = finishedAt; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
}
