package com.onehot.aidrama.users;

import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.mongodb.core.index.Indexed;
import org.springframework.data.mongodb.core.mapping.Document;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Document("accounts")
public class Account {
    public static final int DEFAULT_DAILY_CLAIM_LIMIT = 20;

    @Id
    private String id;
    @Indexed(unique = true)
    private String username;
    private String passwordHash;
    private List<String> roles = new ArrayList<>();
    private boolean enabled = true;
    private Integer dailyClaimLimit = DEFAULT_DAILY_CLAIM_LIMIT;
    private String boundDeviceId;
    private String lastLoginDeviceId;
    private Instant lastLoginAt;
    @CreatedDate
    private Instant createdAt;
    @LastModifiedDate
    private Instant updatedAt;

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }
    public String getPasswordHash() { return passwordHash; }
    public void setPasswordHash(String passwordHash) { this.passwordHash = passwordHash; }
    public List<String> getRoles() { return roles; }
    public void setRoles(List<String> roles) { this.roles = roles; }
    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean enabled) { this.enabled = enabled; }
    public int getDailyClaimLimit() {
        if (dailyClaimLimit == null) {
            return DEFAULT_DAILY_CLAIM_LIMIT;
        }
        return Math.max(dailyClaimLimit, 0);
    }
    public void setDailyClaimLimit(Integer dailyClaimLimit) {
        this.dailyClaimLimit = dailyClaimLimit == null ? DEFAULT_DAILY_CLAIM_LIMIT : Math.max(dailyClaimLimit, 0);
    }
    public String getBoundDeviceId() { return boundDeviceId; }
    public void setBoundDeviceId(String boundDeviceId) { this.boundDeviceId = boundDeviceId; }
    public String getLastLoginDeviceId() { return lastLoginDeviceId; }
    public void setLastLoginDeviceId(String lastLoginDeviceId) { this.lastLoginDeviceId = lastLoginDeviceId; }
    public Instant getLastLoginAt() { return lastLoginAt; }
    public void setLastLoginAt(Instant lastLoginAt) { this.lastLoginAt = lastLoginAt; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
}
