package com.onehot.aidrama.dramas;

import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.mongodb.core.mapping.Document;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Document("dramas")
public class Drama {
    @Id
    private String id;
    private String title;
    private String aiTitle;
    private String summary;
    private String coverUrl;
    private String aiCoverUrl;
    private boolean aiCoverGenerating;
    private Instant aiPreparationFailedAt;
    private Integer rating = 5;
    private Integer totalMinutes;
    private Integer costAmountWan;
    private List<String> categoryIds = new ArrayList<>();
    private String source = "BAIDU_PAN";
    private String sourcePath;
    private DramaStatus status = DramaStatus.DRAFT;
    private List<DramaEpisode> episodes = new ArrayList<>();
    @CreatedDate
    private Instant createdAt;
    @LastModifiedDate
    private Instant updatedAt;

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public String getAiTitle() { return aiTitle; }
    public void setAiTitle(String aiTitle) { this.aiTitle = aiTitle; }
    public String getSummary() { return summary; }
    public void setSummary(String summary) { this.summary = summary; }
    public String getCoverUrl() { return coverUrl; }
    public void setCoverUrl(String coverUrl) { this.coverUrl = coverUrl; }
    public String getAiCoverUrl() { return aiCoverUrl; }
    public void setAiCoverUrl(String aiCoverUrl) { this.aiCoverUrl = aiCoverUrl; }
    public boolean isAiCoverGenerating() { return aiCoverGenerating; }
    public void setAiCoverGenerating(boolean aiCoverGenerating) { this.aiCoverGenerating = aiCoverGenerating; }
    public Instant getAiPreparationFailedAt() { return aiPreparationFailedAt; }
    public void setAiPreparationFailedAt(Instant aiPreparationFailedAt) { this.aiPreparationFailedAt = aiPreparationFailedAt; }
    public Integer getRating() { return rating == null ? 5 : rating; }
    public void setRating(Integer rating) {
        if (rating == null) {
            this.rating = 5;
            return;
        }
        if (rating < 1 || rating > 5) {
            throw new IllegalArgumentException("rating must be between 1 and 5");
        }
        this.rating = rating;
    }
    public Integer getTotalMinutes() { return totalMinutes == null ? 0 : totalMinutes; }
    public void setTotalMinutes(Integer totalMinutes) { this.totalMinutes = totalMinutes == null ? 0 : Math.max(totalMinutes, 0); }
    public Integer getCostAmountWan() { return costAmountWan == null ? 0 : costAmountWan; }
    public void setCostAmountWan(Integer costAmountWan) { this.costAmountWan = costAmountWan == null ? 0 : Math.max(costAmountWan, 0); }
    public List<String> getCategoryIds() { return categoryIds; }
    public void setCategoryIds(List<String> categoryIds) { this.categoryIds = categoryIds; }
    public String getSource() { return source; }
    public void setSource(String source) { this.source = source; }
    public String getSourcePath() { return sourcePath; }
    public void setSourcePath(String sourcePath) { this.sourcePath = sourcePath; }
    public DramaStatus getStatus() { return status; }
    public void setStatus(DramaStatus status) { this.status = status; }
    public List<DramaEpisode> getEpisodes() { return episodes; }
    public void setEpisodes(List<DramaEpisode> episodes) { this.episodes = episodes; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
}
