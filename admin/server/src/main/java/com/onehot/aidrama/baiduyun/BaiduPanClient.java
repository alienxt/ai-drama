package com.onehot.aidrama.baiduyun;

import java.nio.file.Path;
import java.util.List;

public interface BaiduPanClient {
    List<BaiduPanEntry> listDirectory(String remotePath);
    String createStreamingUrl(String remotePath);
    String createDownloadUrl(String remotePath);
    List<String> createDownloadUrls(List<String> remotePaths);
    String readUrl(String url);
    byte[] downloadUrl(String url);
    String readTextFile(String remotePath);
    void downloadFile(String remotePath, Path target);
}
