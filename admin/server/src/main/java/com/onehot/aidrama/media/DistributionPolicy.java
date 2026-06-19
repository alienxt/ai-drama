package com.onehot.aidrama.media;

import java.util.ArrayList;
import java.util.List;

public class DistributionPolicy {
    private List<String> categoryIds = new ArrayList<>();
    private int dailyLimit = 3;
    private int intervalMinutes = 120;
    private boolean enabled = true;
    private String transcodePreset = "wechat-video-default";

    public List<String> getCategoryIds() { return categoryIds; }
    public void setCategoryIds(List<String> categoryIds) { this.categoryIds = categoryIds; }
    public int getDailyLimit() { return dailyLimit; }
    public void setDailyLimit(int dailyLimit) { this.dailyLimit = dailyLimit; }
    public int getIntervalMinutes() { return intervalMinutes; }
    public void setIntervalMinutes(int intervalMinutes) { this.intervalMinutes = intervalMinutes; }
    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean enabled) { this.enabled = enabled; }
    public String getTranscodePreset() { return transcodePreset; }
    public void setTranscodePreset(String transcodePreset) { this.transcodePreset = transcodePreset; }
}

