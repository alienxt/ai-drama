package com.onehot.aidrama.configs;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.mongodb.core.index.Indexed;
import org.springframework.data.mongodb.core.mapping.Document;

import java.time.Instant;

@Document("system_configs")
public class SystemConfig {
    @Id
    private String id;
    @Indexed(unique = true)
    private String key;
    private String value;
    private boolean secret;
    @LastModifiedDate
    private Instant updatedAt;

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getKey() { return key; }
    public void setKey(String key) { this.key = key; }
    public String getValue() { return value; }
    public void setValue(String value) { this.value = value; }
    public boolean isSecret() { return secret; }
    public void setSecret(boolean secret) { this.secret = secret; }
    public Instant getUpdatedAt() { return updatedAt; }
}

