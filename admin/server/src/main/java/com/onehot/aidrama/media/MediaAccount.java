package com.onehot.aidrama.media;

import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.mongodb.core.mapping.Document;

import java.time.Instant;

@Document("media_accounts")
public class MediaAccount {
    @Id
    private String id;
    private String ownerAccountId;
    private MediaPlatform platform;
    private String displayName;
    private String externalAccountId;
    private MediaAccountStatus status = MediaAccountStatus.BINDING;
    private String loginStateRef;
    private String deviceId;
    private Instant lastVerifiedAt;
    private DistributionPolicy distributionPolicy = new DistributionPolicy();
    @CreatedDate
    private Instant createdAt;
    @LastModifiedDate
    private Instant updatedAt;

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getOwnerAccountId() { return ownerAccountId; }
    public void setOwnerAccountId(String ownerAccountId) { this.ownerAccountId = ownerAccountId; }
    public MediaPlatform getPlatform() { return platform; }
    public void setPlatform(MediaPlatform platform) { this.platform = platform; }
    public String getDisplayName() { return displayName; }
    public void setDisplayName(String displayName) { this.displayName = displayName; }
    public String getExternalAccountId() { return externalAccountId; }
    public void setExternalAccountId(String externalAccountId) { this.externalAccountId = externalAccountId; }
    public MediaAccountStatus getStatus() { return status; }
    public void setStatus(MediaAccountStatus status) { this.status = status; }
    public String getLoginStateRef() { return loginStateRef; }
    public void setLoginStateRef(String loginStateRef) { this.loginStateRef = loginStateRef; }
    public String getDeviceId() { return deviceId; }
    public void setDeviceId(String deviceId) { this.deviceId = deviceId; }
    public Instant getLastVerifiedAt() { return lastVerifiedAt; }
    public void setLastVerifiedAt(Instant lastVerifiedAt) { this.lastVerifiedAt = lastVerifiedAt; }
    public DistributionPolicy getDistributionPolicy() { return distributionPolicy; }
    public void setDistributionPolicy(DistributionPolicy distributionPolicy) { this.distributionPolicy = distributionPolicy; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
}
