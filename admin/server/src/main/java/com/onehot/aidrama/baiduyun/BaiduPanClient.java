package com.onehot.aidrama.baiduyun;

import java.nio.file.Path;
import java.util.List;

public interface BaiduPanClient {
    List<BaiduPanEntry> listDirectory(String remotePath);
    String createDownloadUrl(String remotePath);
    List<String> createDownloadUrls(List<String> remotePaths);
    String readTextFile(String remotePath);
    void downloadFile(String remotePath, Path target);
}
