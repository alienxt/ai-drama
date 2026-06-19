package com.onehot.aidrama.dramas;

import java.time.Instant;

public class DramaEpisode {
    private int episodeNo;
    private String title;
    private String sourcePath;
    private Long fsId;
    private long size;
    private Instant downloadUrlExpiresAt;

    public int getEpisodeNo() { return episodeNo; }
    public void setEpisodeNo(int episodeNo) { this.episodeNo = episodeNo; }
    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public String getSourcePath() { return sourcePath; }
    public void setSourcePath(String sourcePath) { this.sourcePath = sourcePath; }
    public Long getFsId() { return fsId; }
    public void setFsId(Long fsId) { this.fsId = fsId; }
    public long getSize() { return size; }
    public void setSize(long size) { this.size = size; }
    public Instant getDownloadUrlExpiresAt() { return downloadUrlExpiresAt; }
    public void setDownloadUrlExpiresAt(Instant downloadUrlExpiresAt) { this.downloadUrlExpiresAt = downloadUrlExpiresAt; }
}

