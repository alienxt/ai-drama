package com.onehot.aidrama.system;

import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.mongodb.core.mapping.Document;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

@Document("system_tasks")
public class SystemTask {
    @Id
    private String id;
    private SystemTaskType type;
    private SystemTaskStatus status = SystemTaskStatus.RUNNING;
    private String title;
    private String triggerSource;
    private String summary;
    private Map<String, Object> requestPayload = new LinkedHashMap<>();
    private Map<String, Object> resultPayload = new LinkedHashMap<>();
    private String errorMessage;
    private Long durationMs;
    private Instant startedAt;
    private Instant finishedAt;
    @CreatedDate
    private Instant createdAt;
    @LastModifiedDate
    private Instant updatedAt;

    public String getId() { return id; }
    public SystemTaskType getType() { return type; }
    public void setType(SystemTaskType type) { this.type = type; }
    public SystemTaskStatus getStatus() { return status; }
    public void setStatus(SystemTaskStatus status) { this.status = status; }
    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public String getTriggerSource() { return triggerSource; }
    public void setTriggerSource(String triggerSource) { this.triggerSource = triggerSource; }
    public String getSummary() { return summary; }
    public void setSummary(String summary) { this.summary = summary; }
    public Map<String, Object> getRequestPayload() { return requestPayload; }
    public void setRequestPayload(Map<String, Object> requestPayload) { this.requestPayload = requestPayload == null ? new LinkedHashMap<>() : requestPayload; }
    public Map<String, Object> getResultPayload() { return resultPayload; }
    public void setResultPayload(Map<String, Object> resultPayload) { this.resultPayload = resultPayload == null ? new LinkedHashMap<>() : resultPayload; }
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
