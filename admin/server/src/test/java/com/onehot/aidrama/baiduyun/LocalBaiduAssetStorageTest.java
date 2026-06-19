package com.onehot.aidrama.baiduyun;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

class LocalBaiduAssetStorageTest {
    @TempDir
    Path uploadDir;

    @Test
    void reusesExistingNonEmptyCoverWithoutDownloadingAgain() throws Exception {
        String remotePath = "/drama/真人剧/2026/6月13日/1.神医归来，开局抢婚校花老婆（80集）吴明宇＆赵慧/0.jpg";
        Path existing = uploadDir.resolve("covers").resolve("be77f38a2ee21393ba7baacb2d4db495.jpg");
        Files.createDirectories(existing.getParent());
        Files.writeString(existing, "existing-cover");
        BaiduPanClient baiduPanClient = mock(BaiduPanClient.class);
        LocalBaiduAssetStorage storage = new LocalBaiduAssetStorage(uploadDir);

        String coverUrl = storage.storeCover(remotePath, baiduPanClient);

        assertThat(coverUrl).isEqualTo("/uploads/covers/be77f38a2ee21393ba7baacb2d4db495.jpg");
        verify(baiduPanClient, never()).downloadFile(remotePath, existing);
    }

    @Test
    void storesUploadedCoverBytesUsingRemotePathName() throws Exception {
        String remotePath = "/drama/真人剧/2026/6月13日/1.神医归来，开局抢婚校花老婆（80集）吴明宇＆赵慧/0.jpg";
        LocalBaiduAssetStorage storage = new LocalBaiduAssetStorage(uploadDir);

        String coverUrl = storage.storeCoverBytes(remotePath, "browser-cover".getBytes());

        Path stored = uploadDir.resolve("covers").resolve("be77f38a2ee21393ba7baacb2d4db495.jpg");
        assertThat(coverUrl).isEqualTo("/uploads/covers/be77f38a2ee21393ba7baacb2d4db495.jpg");
        assertThat(Files.readString(stored)).isEqualTo("browser-cover");
    }
}
