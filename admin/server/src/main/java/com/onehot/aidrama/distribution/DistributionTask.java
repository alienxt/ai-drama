package com.onehot.aidrama.distribution;

import com.onehot.aidrama.media.MediaPlatform;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.mongodb.core.mapping.Document;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Document("distribution_tasks")
public class DistributionTask {
    @Id
    private String id;
    private String mediaAccountId;
    private MediaPlatform platform;
    private String dramaId;
    private List<Integer> episodeRange = new ArrayList<>();
    private DistributionTaskStatus status = DistributionTaskStatus.PENDING;
    private String lockedByDeviceId;
    private int progress;
    private int priority;
    private String failureReason;
    private String platformPublishId;
    private Instant platformSubmittedAt;
    private Instant finishedAt;
    @CreatedDate
    private Instant createdAt;
    @LastModifiedDate
    private Instant updatedAt;

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getMediaAccountId() { return mediaAccountId; }
    public void setMediaAccountId(String mediaAccountId) { this.mediaAccountId = mediaAccountId; }
    public MediaPlatform getPlatform() { return platform; }
    public void setPlatform(MediaPlatform platform) { this.platform = platform; }
    public String getDramaId() { return dramaId; }
    public void setDramaId(String dramaId) { this.dramaId = dramaId; }
    public List<Integer> getEpisodeRange() { return episodeRange; }
    public void setEpisodeRange(List<Integer> episodeRange) { this.episodeRange = episodeRange; }
    public DistributionTaskStatus getStatus() { return status; }
    public void setStatus(DistributionTaskStatus status) { this.status = status; }
    public String getLockedByDeviceId() { return lockedByDeviceId; }
    public void setLockedByDeviceId(String lockedByDeviceId) { this.lockedByDeviceId = lockedByDeviceId; }
    public int getProgress() { return progress; }
    public void setProgress(int progress) { this.progress = progress; }
    public int getPriority() { return priority; }
    public void setPriority(int priority) { this.priority = priority; }
    public String getFailureReason() { return failureReason; }
    public void setFailureReason(String failureReason) { this.failureReason = failureReason; }
    public String getPlatformPublishId() { return platformPublishId; }
    public void setPlatformPublishId(String platformPublishId) { this.platformPublishId = platformPublishId; }
    public Instant getPlatformSubmittedAt() { return platformSubmittedAt; }
    public void setPlatformSubmittedAt(Instant platformSubmittedAt) { this.platformSubmittedAt = platformSubmittedAt; }
    public Instant getFinishedAt() { return finishedAt; }
    public void setFinishedAt(Instant finishedAt) { this.finishedAt = finishedAt; }
    public Instant getCreatedAt() { return createdAt; }
    public void setCreatedAt(Instant createdAt) { this.createdAt = createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Instant updatedAt) { this.updatedAt = updatedAt; }
}
