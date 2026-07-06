package com.onehot.aidrama.hongguo;

import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Document("hongguo_drama_candidates")
@CompoundIndex(name = "provider_drama_id_idx", def = "{'provider': 1, 'providerDramaId': 1}", unique = true)
public class HongguoDramaCandidate {
    @Id
    private String id;
    private String provider = HongguoDramaService.PROVIDER;
    private String providerDramaId;
    private String title;
    private String summary;
    private String coverUrl;
    private String duration;
    private String score;
    private String category;
    private String copyright;
    private Integer episodeCount;
    private Long playCount;
    private List<String> categories = new ArrayList<>();
    private String calendarDate;
    private Integer calendarPage;
    private String searchKeyword;
    private Integer searchPage;
    private Instant publishedAt;
    private HongguoCandidateStatus status = HongguoCandidateStatus.NEW;
    private String importedDramaId;
    @CreatedDate
    private Instant createdAt;
    @LastModifiedDate
    private Instant updatedAt;

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getProvider() { return provider; }
    public void setProvider(String provider) { this.provider = provider; }
    public String getProviderDramaId() { return providerDramaId; }
    public void setProviderDramaId(String providerDramaId) { this.providerDramaId = providerDramaId; }
    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public String getSummary() { return summary; }
    public void setSummary(String summary) { this.summary = summary; }
    public String getCoverUrl() { return coverUrl; }
    public void setCoverUrl(String coverUrl) { this.coverUrl = coverUrl; }
    public String getDuration() { return duration; }
    public void setDuration(String duration) { this.duration = duration; }
    public String getScore() { return score; }
    public void setScore(String score) { this.score = score; }
    public String getCategory() { return category; }
    public void setCategory(String category) { this.category = category; }
    public String getCopyright() { return copyright; }
    public void setCopyright(String copyright) { this.copyright = copyright; }
    public Integer getEpisodeCount() { return episodeCount; }
    public void setEpisodeCount(Integer episodeCount) { this.episodeCount = episodeCount; }
    public Long getPlayCount() { return playCount; }
    public void setPlayCount(Long playCount) { this.playCount = playCount; }
    public List<String> getCategories() { return categories; }
    public void setCategories(List<String> categories) { this.categories = categories == null ? List.of() : categories; }
    public String getCalendarDate() { return calendarDate; }
    public void setCalendarDate(String calendarDate) { this.calendarDate = calendarDate; }
    public Integer getCalendarPage() { return calendarPage; }
    public void setCalendarPage(Integer calendarPage) { this.calendarPage = calendarPage; }
    public String getSearchKeyword() { return searchKeyword; }
    public void setSearchKeyword(String searchKeyword) { this.searchKeyword = searchKeyword; }
    public Integer getSearchPage() { return searchPage; }
    public void setSearchPage(Integer searchPage) { this.searchPage = searchPage; }
    public Instant getPublishedAt() { return publishedAt; }
    public void setPublishedAt(Instant publishedAt) { this.publishedAt = publishedAt; }
    public HongguoCandidateStatus getStatus() { return status == null ? HongguoCandidateStatus.NEW : status; }
    public void setStatus(HongguoCandidateStatus status) { this.status = status; }
    public String getImportedDramaId() { return importedDramaId; }
    public void setImportedDramaId(String importedDramaId) { this.importedDramaId = importedDramaId; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
}
