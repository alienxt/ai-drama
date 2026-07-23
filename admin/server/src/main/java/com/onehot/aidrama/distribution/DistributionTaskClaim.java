package com.onehot.aidrama.distribution;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

import java.time.Instant;

@Document("distribution_task_claims")
public class DistributionTaskClaim {
    @Id
    private String id;
    private String taskId;
    private String mediaAccountId;
    private String deviceId;
    private Instant claimedAt;

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getTaskId() { return taskId; }
    public void setTaskId(String taskId) { this.taskId = taskId; }
    public String getMediaAccountId() { return mediaAccountId; }
    public void setMediaAccountId(String mediaAccountId) { this.mediaAccountId = mediaAccountId; }
    public String getDeviceId() { return deviceId; }
    public void setDeviceId(String deviceId) { this.deviceId = deviceId; }
    public Instant getClaimedAt() { return claimedAt; }
    public void setClaimedAt(Instant claimedAt) { this.claimedAt = claimedAt; }
}
