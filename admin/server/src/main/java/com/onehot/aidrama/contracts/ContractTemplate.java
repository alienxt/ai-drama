package com.onehot.aidrama.contracts;

import com.onehot.aidrama.media.MediaPlatform;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.mongodb.core.index.Indexed;
import org.springframework.data.mongodb.core.mapping.Document;

import java.time.Instant;

@Document("contract_templates")
public class ContractTemplate {
    @Id
    private String id;
    @Indexed
    private MediaPlatform platform = MediaPlatform.WECHAT_VIDEO;
    @Indexed
    private ContractTemplateType type;
    private String name;
    private String fileName;
    private long fileSize;
    private String downloadUrl;
    private Instant uploadedAt;
    @CreatedDate
    private Instant createdAt;
    @LastModifiedDate
    private Instant updatedAt;

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public MediaPlatform getPlatform() { return platform; }
    public void setPlatform(MediaPlatform platform) { this.platform = platform; }
    public ContractTemplateType getType() { return type; }
    public void setType(ContractTemplateType type) { this.type = type; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public String getFileName() { return fileName; }
    public void setFileName(String fileName) { this.fileName = fileName; }
    public long getFileSize() { return fileSize; }
    public void setFileSize(long fileSize) { this.fileSize = fileSize; }
    public String getDownloadUrl() { return downloadUrl; }
    public void setDownloadUrl(String downloadUrl) { this.downloadUrl = downloadUrl; }
    public Instant getUploadedAt() { return uploadedAt; }
    public void setUploadedAt(Instant uploadedAt) { this.uploadedAt = uploadedAt; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
}
