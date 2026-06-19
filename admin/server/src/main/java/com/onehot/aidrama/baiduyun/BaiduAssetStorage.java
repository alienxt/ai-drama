package com.onehot.aidrama.baiduyun;

public interface BaiduAssetStorage {
    String storeCover(String remotePath, BaiduPanClient baiduPanClient);
    String storeCoverBytes(String remotePath, byte[] bytes);
}
