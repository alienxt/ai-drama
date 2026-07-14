package com.onehot.aidrama.baiduyun;

import com.onehot.aidrama.configs.SystemConfigService;
import com.onehot.aidrama.dramas.Drama;
import com.onehot.aidrama.dramas.DramaEpisode;
import com.onehot.aidrama.dramas.DramaRepository;
import com.onehot.aidrama.dramas.DramaStatus;
import com.onehot.aidrama.system.SystemTaskService;
import com.onehot.aidrama.system.SystemTaskType;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class BaiduDramaScannerTest {
    @Test
    void importsLocalCoverUrlAndSummaryTextFromDramaDirectory() {
        BaiduPanClient baiduPanClient = mock(BaiduPanClient.class);
        DramaRepository dramaRepository = mock(DramaRepository.class);
        SystemConfigService configService = mock(SystemConfigService.class);
        BaiduAssetStorage assetStorage = mock(BaiduAssetStorage.class);
        BaiduDramaScanner scanner = new BaiduDramaScanner(baiduPanClient, dramaRepository, configService, assetStorage);

        when(baiduPanClient.listDirectory("/root/6月15日")).thenReturn(List.of(
                new BaiduPanEntry("/root/6月15日/1.神医归来（80集）", "1.神医归来（80集）", true, 1L, 0)
        ));
        when(baiduPanClient.listDirectory("/root/6月15日/1.神医归来（80集）")).thenReturn(List.of(
                new BaiduPanEntry("/root/6月15日/1.神医归来（80集）/cover.jpg", "cover.jpg", false, 2L, 100),
                new BaiduPanEntry("/root/6月15日/1.神医归来（80集）/简介.txt", "简介.txt", false, 3L, 100),
                new BaiduPanEntry("/root/6月15日/1.神医归来（80集）/01.mp4", "01.mp4", false, 4L, 100)
        ));
        when(assetStorage.storeCover("/root/6月15日/1.神医归来（80集）/cover.jpg", baiduPanClient)).thenReturn("/uploads/covers/cover.jpg");
        when(baiduPanClient.readTextFile("/root/6月15日/1.神医归来（80集）/简介.txt")).thenReturn("真正的剧情简介");
        when(dramaRepository.findAllBySourcePath("/root/6月15日/1.神医归来（80集）")).thenReturn(List.of());
        when(dramaRepository.save(any(Drama.class))).thenAnswer(invocation -> invocation.getArgument(0));

        Drama imported = scanner.scanDateDirectory("/root/6月15日").getFirst();

        assertThat(imported.getCoverUrl()).isEqualTo("/uploads/covers/cover.jpg");
        assertThat(imported.getSummary()).isEqualTo("真正的剧情简介");
        assertThat(imported.getStatus()).isEqualTo(DramaStatus.DRAFT);
        assertThat(imported.getTotalMinutes()).isEqualTo(10);
    }

    @Test
    void skipsSummaryAndCoverDownloadWhenScanDownloadAssetsIsDisabled() {
        BaiduPanClient baiduPanClient = mock(BaiduPanClient.class);
        DramaRepository dramaRepository = mock(DramaRepository.class);
        SystemConfigService configService = mock(SystemConfigService.class);
        BaiduAssetStorage assetStorage = mock(BaiduAssetStorage.class);
        BaiduDramaScanner scanner = new BaiduDramaScanner(baiduPanClient, dramaRepository, configService, assetStorage);

        when(configService.get("baidu.scanDownloadAssets")).thenReturn(Optional.of("false"));
        when(baiduPanClient.listDirectory("/root/6月15日")).thenReturn(List.of(
                new BaiduPanEntry("/root/6月15日/1.神医归来（80集）", "1.神医归来（80集）", true, 1L, 0)
        ));
        when(baiduPanClient.listDirectory("/root/6月15日/1.神医归来（80集）")).thenReturn(List.of(
                new BaiduPanEntry("/root/6月15日/1.神医归来（80集）/cover.jpg", "cover.jpg", false, 2L, 100),
                new BaiduPanEntry("/root/6月15日/1.神医归来（80集）/简介.txt", "简介.txt", false, 3L, 100),
                new BaiduPanEntry("/root/6月15日/1.神医归来（80集）/01.mp4", "01.mp4", false, 4L, 100)
        ));
        when(dramaRepository.findAllBySourcePath("/root/6月15日/1.神医归来（80集）")).thenReturn(List.of());
        when(dramaRepository.save(any(Drama.class))).thenAnswer(invocation -> invocation.getArgument(0));

        Drama imported = scanner.scanDateDirectory("/root/6月15日").getFirst();

        assertThat(imported.getSummary()).isEqualTo("神医归来（80集）");
        assertThat(imported.getCoverUrl()).isNull();
        verify(baiduPanClient, never()).readTextFile(any());
        verify(assetStorage, never()).storeCover(any(), any());
    }

    @Test
    void skipsSingleBrokenDramaDirectoryAndContinuesScanningOthers() {
        BaiduPanClient baiduPanClient = mock(BaiduPanClient.class);
        DramaRepository dramaRepository = mock(DramaRepository.class);
        SystemConfigService configService = mock(SystemConfigService.class);
        BaiduAssetStorage assetStorage = mock(BaiduAssetStorage.class);
        BaiduDramaScanner scanner = new BaiduDramaScanner(baiduPanClient, dramaRepository, configService, assetStorage);

        when(baiduPanClient.listDirectory("/root/6月15日")).thenReturn(List.of(
                new BaiduPanEntry("/root/6月15日/1.百度返回-9（61集）尹洋&邬倩", "1.百度返回-9（61集）尹洋&邬倩", true, 1L, 0),
                new BaiduPanEntry("/root/6月15日/2.正常短剧（20集）", "2.正常短剧（20集）", true, 2L, 0)
        ));
        when(baiduPanClient.listDirectory("/root/6月15日/1.百度返回-9（61集）尹洋&邬倩"))
                .thenThrow(new BaiduPanException("Baidu API error -9 for https://pan.baidu.com/rest/2.0/xpan/file?access_token=***"));
        when(baiduPanClient.listDirectory("/root/6月15日/2.正常短剧（20集）")).thenReturn(List.of(
                new BaiduPanEntry("/root/6月15日/2.正常短剧（20集）/01.mp4", "01.mp4", false, 4L, 100)
        ));
        when(dramaRepository.findAllBySourcePath("/root/6月15日/2.正常短剧（20集）")).thenReturn(List.of());
        when(dramaRepository.save(any(Drama.class))).thenAnswer(invocation -> invocation.getArgument(0));

        List<Drama> imported = scanner.scanDateDirectory("/root/6月15日");

        assertThat(imported).hasSize(1);
        assertThat(imported.getFirst().getSourcePath()).isEqualTo("/root/6月15日/2.正常短剧（20集）");
        verify(dramaRepository, never()).findAllBySourcePath("/root/6月15日/1.百度返回-9（61集）尹洋&邬倩");
    }

    @Test
    void descendsCategoryFolderInsteadOfImportingItAsZeroEpisodeDrama() {
        BaiduPanClient baiduPanClient = mock(BaiduPanClient.class);
        DramaRepository dramaRepository = mock(DramaRepository.class);
        SystemConfigService configService = mock(SystemConfigService.class);
        BaiduAssetStorage assetStorage = mock(BaiduAssetStorage.class);
        BaiduDramaScanner scanner = new BaiduDramaScanner(baiduPanClient, dramaRepository, configService, assetStorage);

        when(baiduPanClient.listDirectory("/root/6月20日")).thenReturn(List.of(
                new BaiduPanEntry("/root/6月20日/甜宠情感", "甜宠情感", true, 1L, 0)
        ));
        when(baiduPanClient.listDirectory("/root/6月20日/甜宠情感")).thenReturn(List.of(
                new BaiduPanEntry("/root/6月20日/甜宠情感/1.错嫁甜妻（2集）", "1.错嫁甜妻（2集）", true, 2L, 0)
        ));
        when(baiduPanClient.listDirectory("/root/6月20日/甜宠情感/1.错嫁甜妻（2集）")).thenReturn(List.of(
                new BaiduPanEntry("/root/6月20日/甜宠情感/1.错嫁甜妻（2集）/第1集.mp4", "第1集.mp4", false, 3L, 100),
                new BaiduPanEntry("/root/6月20日/甜宠情感/1.错嫁甜妻（2集）/EP02.mkv", "EP02.mkv", false, 4L, 100)
        ));
        when(dramaRepository.findAllBySourcePath("/root/6月20日/甜宠情感/1.错嫁甜妻（2集）")).thenReturn(List.of());
        when(dramaRepository.save(any(Drama.class))).thenAnswer(invocation -> invocation.getArgument(0));

        List<Drama> imported = scanner.scanDateDirectory("/root/6月20日");

        assertThat(imported).hasSize(1);
        Drama drama = imported.getFirst();
        assertThat(drama.getTitle()).isEqualTo("错嫁甜妻");
        assertThat(drama.getSourcePath()).isEqualTo("/root/6月20日/甜宠情感/1.错嫁甜妻（2集）");
        assertThat(drama.getEpisodes()).extracting(DramaEpisode::getEpisodeNo).containsExactly(1, 2);
        verify(dramaRepository, never()).findAllBySourcePath("/root/6月20日/甜宠情感");
    }

    @Test
    void skipsLeafDirectoryWhenNoEpisodeFilesAreFound() {
        BaiduPanClient baiduPanClient = mock(BaiduPanClient.class);
        DramaRepository dramaRepository = mock(DramaRepository.class);
        SystemConfigService configService = mock(SystemConfigService.class);
        BaiduAssetStorage assetStorage = mock(BaiduAssetStorage.class);
        BaiduDramaScanner scanner = new BaiduDramaScanner(baiduPanClient, dramaRepository, configService, assetStorage);

        when(baiduPanClient.listDirectory("/root/6月20日")).thenReturn(List.of(
                new BaiduPanEntry("/root/6月20日/空目录", "空目录", true, 1L, 0)
        ));
        when(baiduPanClient.listDirectory("/root/6月20日/空目录")).thenReturn(List.of(
                new BaiduPanEntry("/root/6月20日/空目录/cover.jpg", "cover.jpg", false, 2L, 100),
                new BaiduPanEntry("/root/6月20日/空目录/简介.txt", "简介.txt", false, 3L, 100)
        ));

        List<Drama> imported = scanner.scanDateDirectory("/root/6月20日");

        assertThat(imported).isEmpty();
        verify(dramaRepository, never()).save(any(Drama.class));
    }

    @Test
    void failedLatestDateScanDoesNotUpdateLastScanTime() {
        BaiduPanClient baiduPanClient = mock(BaiduPanClient.class);
        DramaRepository dramaRepository = mock(DramaRepository.class);
        SystemConfigService configService = mock(SystemConfigService.class);
        BaiduAssetStorage assetStorage = mock(BaiduAssetStorage.class);
        BaiduDramaScanner scanner = new BaiduDramaScanner(baiduPanClient, dramaRepository, configService, assetStorage);
        when(baiduPanClient.listDirectory("/root")).thenThrow(new BaiduPanException("Baidu API error"));

        org.assertj.core.api.Assertions.assertThatThrownBy(() -> scanner.scanLatestDate("/root"))
                .isInstanceOf(BaiduPanException.class);

        verifyNoInteractions(configService);
    }

    @Test
    void fallsBackToPlannedSummaryWhenDownloadedSummaryIsBaiduErrorJson() {
        BaiduPanClient baiduPanClient = mock(BaiduPanClient.class);
        DramaRepository dramaRepository = mock(DramaRepository.class);
        SystemConfigService configService = mock(SystemConfigService.class);
        BaiduAssetStorage assetStorage = mock(BaiduAssetStorage.class);
        BaiduDramaScanner scanner = new BaiduDramaScanner(baiduPanClient, dramaRepository, configService, assetStorage);

        when(baiduPanClient.listDirectory("/root/6月15日")).thenReturn(List.of(
                new BaiduPanEntry("/root/6月15日/2.花瓶千年第 三季（45集）主演", "2.花瓶千年第三季（45集）主演", true, 1L, 0)
        ));
        when(baiduPanClient.listDirectory("/root/6月15日/2.花瓶千年第 三季（45集）主演")).thenReturn(List.of(
                new BaiduPanEntry("/root/6月15日/2.花瓶千年第 三季（45集）主演/简介.txt", "简介.txt", false, 3L, 100),
                new BaiduPanEntry("/root/6月15日/2.花瓶千年第 三季（45集）主演/01.mp4", "01.mp4", false, 4L, 100)
        ));
        when(baiduPanClient.readTextFile("/root/6月15日/2.花瓶千年第 三季（45集）主演/简介.txt"))
                .thenReturn("{\"error_code\":302,\"request_id\":378608807925327015}");
        when(dramaRepository.findAllBySourcePath("/root/6月15日/2.花瓶千年第 三季（45集）主演")).thenReturn(List.of());
        when(dramaRepository.save(any(Drama.class))).thenAnswer(invocation -> invocation.getArgument(0));

        Drama imported = scanner.scanDateDirectory("/root/6月15日").getFirst();

        assertThat(imported.getSummary()).isEqualTo("花瓶千年第三季（45集）主演");
    }

    @Test
    void rescanningExistingDramaDoesNotClearExistingTitleSummaryOrCoverWhenAssetsAreMissing() {
        BaiduPanClient baiduPanClient = mock(BaiduPanClient.class);
        DramaRepository dramaRepository = mock(DramaRepository.class);
        SystemConfigService configService = mock(SystemConfigService.class);
        BaiduAssetStorage assetStorage = mock(BaiduAssetStorage.class);
        BaiduDramaScanner scanner = new BaiduDramaScanner(baiduPanClient, dramaRepository, configService, assetStorage);
        Drama existing = new Drama();
        existing.setTitle("后台维护标题");
        existing.setSummary("后台维护简介");
        existing.setCoverUrl("/uploads/covers/existing.jpg");
        existing.setSourcePath("/root/6月15日/3.重新扫描会缺素材（20集）");

        when(baiduPanClient.listDirectory("/root/6月15日")).thenReturn(List.of(
                new BaiduPanEntry("/root/6月15日/3.重新扫描会缺素材（20集）", "3.重新扫描会缺素材（20集）", true, 1L, 0)
        ));
        when(baiduPanClient.listDirectory("/root/6月15日/3.重新扫描会缺素材（20集）")).thenReturn(List.of(
                new BaiduPanEntry("/root/6月15日/3.重新扫描会缺素材（20集）/01.mp4", "01.mp4", false, 4L, 100)
        ));
        when(dramaRepository.findAllBySourcePath("/root/6月15日/3.重新扫描会缺素材（20集）")).thenReturn(List.of(existing));
        when(dramaRepository.save(any(Drama.class))).thenAnswer(invocation -> invocation.getArgument(0));

        Drama rescanned = scanner.scanDateDirectory("/root/6月15日").getFirst();

        assertThat(rescanned.getTitle()).isEqualTo("后台维护标题");
        assertThat(rescanned.getSummary()).isEqualTo("后台维护简介");
        assertThat(rescanned.getCoverUrl()).isEqualTo("/uploads/covers/existing.jpg");
    }

    @Test
    void rescanningExistingReadyDramaPreservesReadyStatus() {
        BaiduPanClient baiduPanClient = mock(BaiduPanClient.class);
        DramaRepository dramaRepository = mock(DramaRepository.class);
        SystemConfigService configService = mock(SystemConfigService.class);
        BaiduAssetStorage assetStorage = mock(BaiduAssetStorage.class);
        BaiduDramaScanner scanner = new BaiduDramaScanner(baiduPanClient, dramaRepository, configService, assetStorage);
        Drama existing = new Drama();
        existing.setTitle("已准备短剧");
        existing.setSummary("已有简介");
        existing.setCoverUrl("/uploads/covers/existing.jpg");
        existing.setAiTitle("AI 剧名");
        existing.setAiCoverUrl("/uploads/ai-covers/existing.jpg");
        existing.setStatus(DramaStatus.READY);
        existing.setSourcePath("/root/6月15日/4.已准备短剧（20集）");

        when(baiduPanClient.listDirectory("/root/6月15日")).thenReturn(List.of(
                new BaiduPanEntry("/root/6月15日/4.已准备短剧（20集）", "4.已准备短剧（20集）", true, 1L, 0)
        ));
        when(baiduPanClient.listDirectory("/root/6月15日/4.已准备短剧（20集）")).thenReturn(List.of(
                new BaiduPanEntry("/root/6月15日/4.已准备短剧（20集）/01.mp4", "01.mp4", false, 4L, 100)
        ));
        when(dramaRepository.findAllBySourcePath("/root/6月15日/4.已准备短剧（20集）")).thenReturn(List.of(existing));
        when(dramaRepository.save(any(Drama.class))).thenAnswer(invocation -> invocation.getArgument(0));

        Drama rescanned = scanner.scanDateDirectory("/root/6月15日").getFirst();

        assertThat(rescanned.getStatus()).isEqualTo(DramaStatus.READY);
    }

    @Test
    void rescanningDuplicateSourcePathKeepsUsingExistingRecordInsteadOfExpectingUniqueResult() {
        BaiduPanClient baiduPanClient = mock(BaiduPanClient.class);
        DramaRepository dramaRepository = mock(DramaRepository.class);
        SystemConfigService configService = mock(SystemConfigService.class);
        BaiduAssetStorage assetStorage = mock(BaiduAssetStorage.class);
        BaiduDramaScanner scanner = new BaiduDramaScanner(baiduPanClient, dramaRepository, configService, assetStorage);
        Drama first = new Drama();
        first.setId("drama-1");
        first.setTitle("保留的后台标题");
        first.setSourcePath("/root/6月19日/1.神医归来（80集）");
        Drama duplicate = new Drama();
        duplicate.setId("drama-2");
        duplicate.setTitle("重复记录");
        duplicate.setSourcePath("/root/6月19日/1.神医归来（80集）");

        when(baiduPanClient.listDirectory("/root/6月19日")).thenReturn(List.of(
                new BaiduPanEntry("/root/6月19日/1.神医归来（80集）", "1.神医归来（80集）", true, 1L, 0)
        ));
        when(baiduPanClient.listDirectory("/root/6月19日/1.神医归来（80集）")).thenReturn(List.of(
                new BaiduPanEntry("/root/6月19日/1.神医归来（80集）/01.mp4", "01.mp4", false, 4L, 100)
        ));
        when(dramaRepository.findAllBySourcePath("/root/6月19日/1.神医归来（80集）")).thenReturn(List.of(first, duplicate));
        when(dramaRepository.save(any(Drama.class))).thenAnswer(invocation -> invocation.getArgument(0));

        Drama rescanned = scanner.scanDateDirectory("/root/6月19日").getFirst();

        assertThat(rescanned).isSameAs(first);
        assertThat(rescanned.getTitle()).isEqualTo("保留的后台标题");
        assertThat(rescanned.getEpisodes()).hasSize(1);
        verify(dramaRepository).save(first);
        verify(dramaRepository, never()).save(duplicate);
    }

    @Test
    void skipsDramaWhenOriginalTitleAndEpisodeCountAlreadyExistOnDifferentSourcePath() {
        BaiduPanClient baiduPanClient = mock(BaiduPanClient.class);
        DramaRepository dramaRepository = mock(DramaRepository.class);
        SystemConfigService configService = mock(SystemConfigService.class);
        BaiduAssetStorage assetStorage = mock(BaiduAssetStorage.class);
        BaiduDramaScanner scanner = new BaiduDramaScanner(baiduPanClient, dramaRepository, configService, assetStorage);
        Drama existing = new Drama();
        existing.setId("drama-1");
        existing.setTitle("山风入京华");
        existing.setSourcePath("/root/6月18日/1.山风入京华（5集）");
        existing.setEpisodes(List.of(episode(1), episode(2), episode(3), episode(4), episode(5)));

        when(baiduPanClient.listDirectory("/root/6月19日")).thenReturn(List.of(
                new BaiduPanEntry("/root/6月19日/2.山风入京华（5集）", "2.山风入京华（5集）", true, 1L, 0)
        ));
        when(baiduPanClient.listDirectory("/root/6月19日/2.山风入京华（5集）")).thenReturn(List.of(
                new BaiduPanEntry("/root/6月19日/2.山风入京华（5集）/01.mp4", "01.mp4", false, 4L, 100),
                new BaiduPanEntry("/root/6月19日/2.山风入京华（5集）/02.mp4", "02.mp4", false, 5L, 100),
                new BaiduPanEntry("/root/6月19日/2.山风入京华（5集）/03.mp4", "03.mp4", false, 6L, 100),
                new BaiduPanEntry("/root/6月19日/2.山风入京华（5集）/04.mp4", "04.mp4", false, 7L, 100),
                new BaiduPanEntry("/root/6月19日/2.山风入京华（5集）/05.mp4", "05.mp4", false, 8L, 100)
        ));
        when(dramaRepository.findAllBySourcePath("/root/6月19日/2.山风入京华（5集）")).thenReturn(List.of());
        when(dramaRepository.findAllByTitle("山风入京华")).thenReturn(List.of(existing));
        when(dramaRepository.save(any(Drama.class))).thenAnswer(invocation -> invocation.getArgument(0));

        List<Drama> imported = scanner.scanDateDirectory("/root/6月19日");

        assertThat(imported).isEmpty();
        verify(dramaRepository, never()).save(any(Drama.class));
    }

    @Test
    void repairsImportedBaiduCoverAndErrorSummaryFromExistingSourcePath() {
        BaiduPanClient baiduPanClient = mock(BaiduPanClient.class);
        DramaRepository dramaRepository = mock(DramaRepository.class);
        SystemConfigService configService = mock(SystemConfigService.class);
        BaiduAssetStorage assetStorage = mock(BaiduAssetStorage.class);
        BaiduDramaScanner scanner = new BaiduDramaScanner(baiduPanClient, dramaRepository, configService, assetStorage);
        Drama old = new Drama();
        old.setTitle("厨娘炸厨房，仙尊宠上天");
        old.setSourcePath("/root/6月13日/10.厨娘炸厨房，仙尊宠上天（34集）");
        old.setSummary("{\"error_code\":302,\"request_id\":37884274703895353}");
        old.setCoverUrl("https://pan.baidu.com/rest/2.0/xpan/file?method=filemanager");

        when(dramaRepository.findAll()).thenReturn(List.of(old));
        when(baiduPanClient.listDirectory("/root/6月13日/10.厨娘炸厨房，仙尊宠上天（34集）")).thenReturn(List.of(
                new BaiduPanEntry("/root/6月13日/10.厨娘炸厨房，仙尊宠上天（34集）/cover.jpg", "cover.jpg", false, 2L, 100),
                new BaiduPanEntry("/root/6月13日/10.厨娘炸厨房，仙尊宠上天（34集）/简介.txt", "简介.txt", false, 3L, 100),
                new BaiduPanEntry("/root/6月13日/10.厨娘炸厨房，仙尊宠上天（34集）/01.mp4", "01.mp4", false, 4L, 100)
        ));
        when(baiduPanClient.readTextFile("/root/6月13日/10.厨娘炸厨房，仙尊宠上天（34集）/简介.txt"))
                .thenReturn("{\"error_code\":302,\"request_id\":37884274703895353}");
        when(assetStorage.storeCover("/root/6月13日/10.厨娘炸厨房，仙尊宠上天（34集）/cover.jpg", baiduPanClient))
                .thenReturn("/uploads/covers/fixed.jpg");
        when(dramaRepository.save(any(Drama.class))).thenAnswer(invocation -> invocation.getArgument(0));

        Drama repaired = scanner.repairImportedAssets().getFirst();

        assertThat(repaired.getCoverUrl()).isEqualTo("/uploads/covers/fixed.jpg");
        assertThat(repaired.getSummary()).isEqualTo("厨娘炸厨房，仙尊宠上天（34集）");
    }

    @Test
    void syncsCoverAndSummaryForSelectedDramasAndReportsFailures() {
        BaiduPanClient baiduPanClient = mock(BaiduPanClient.class);
        DramaRepository dramaRepository = mock(DramaRepository.class);
        SystemConfigService configService = mock(SystemConfigService.class);
        BaiduAssetStorage assetStorage = mock(BaiduAssetStorage.class);
        BaiduDramaScanner scanner = new BaiduDramaScanner(baiduPanClient, dramaRepository, configService, assetStorage);
        Drama first = new Drama();
        first.setId("drama-1");
        first.setTitle("旧剧名");
        first.setSummary("旧简介");
        first.setCoverUrl("/uploads/covers/old.jpg");
        first.setAiTitle("AI 剧名保留");
        first.setAiCoverUrl("/uploads/ai-cover.jpg");
        first.setSourcePath("/root/6月15日/1.神医归来（80集）");
        Drama missing = new Drama();
        missing.setId("drama-2");
        missing.setTitle("缺少源目录");

        when(dramaRepository.findAllById(any())).thenReturn(List.of(first, missing));
        when(baiduPanClient.listDirectory("/root/6月15日/1.神医归来（80集）")).thenReturn(List.of(
                new BaiduPanEntry("/root/6月15日/1.神医归来（80集）/cover.png", "cover.png", false, 2L, 100),
                new BaiduPanEntry("/root/6月15日/1.神医归来（80集）/summary.md", "summary.md", false, 3L, 100),
                new BaiduPanEntry("/root/6月15日/1.神医归来（80集）/01.mp4", "01.mp4", false, 4L, 100)
        ));
        when(baiduPanClient.readTextFile("/root/6月15日/1.神医归来（80集）/summary.md")).thenReturn("同步后的简介");
        when(assetStorage.storeCover("/root/6月15日/1.神医归来（80集）/cover.png", baiduPanClient))
                .thenReturn("/uploads/covers/synced.png");
        when(dramaRepository.save(any(Drama.class))).thenAnswer(invocation -> invocation.getArgument(0));

        BaiduDramaScanner.SyncResult result = scanner.syncImportedAssets(List.of("drama-1", "drama-2", "unknown-id"));

        assertThat(result.requested()).isEqualTo(3);
        assertThat(result.succeeded()).isEqualTo(1);
        assertThat(result.failed()).isEqualTo(2);
        assertThat(result.dramas()).containsExactly(first);
        assertThat(first.getSummary()).isEqualTo("同步后的简介");
        assertThat(first.getCoverUrl()).isEqualTo("/uploads/covers/synced.png");
        assertThat(first.getAiTitle()).isEqualTo("AI 剧名保留");
        assertThat(first.getAiCoverUrl()).isEqualTo("/uploads/ai-cover.jpg");
    }

    @Test
    void selectedAssetSyncFailsWhenZeroCoverDownloadFailsAndPreservesExistingCover() {
        BaiduPanClient baiduPanClient = mock(BaiduPanClient.class);
        DramaRepository dramaRepository = mock(DramaRepository.class);
        SystemConfigService configService = mock(SystemConfigService.class);
        BaiduAssetStorage assetStorage = mock(BaiduAssetStorage.class);
        BaiduDramaScanner scanner = new BaiduDramaScanner(baiduPanClient, dramaRepository, configService, assetStorage);
        Drama drama = new Drama();
        drama.setId("drama-1");
        drama.setTitle("神医归来，开局抢婚校花老婆");
        drama.setCoverUrl("/uploads/covers/old.jpg");
        drama.setSourcePath("/root/6月19日/1.神医归来，开局抢婚校花老婆（80集）");

        when(dramaRepository.findAllById(any())).thenReturn(List.of(drama));
        when(baiduPanClient.listDirectory("/root/6月19日/1.神医归来，开局抢婚校花老婆（80集）")).thenReturn(List.of(
                new BaiduPanEntry("/root/6月19日/1.神医归来，开局抢婚校花老婆（80集）/0.jpg", "0.jpg", false, 2L, 100),
                new BaiduPanEntry("/root/6月19日/1.神医归来，开局抢婚校花老婆（80集）/01.mp4", "01.mp4", false, 4L, 100)
        ));
        when(assetStorage.storeCover("/root/6月19日/1.神医归来，开局抢婚校花老婆（80集）/0.jpg", baiduPanClient))
                .thenThrow(new BaiduPanException("Baidu file download HTTP 403"));

        BaiduDramaScanner.SyncResult result = scanner.syncImportedAssets(List.of("drama-1"));

        assertThat(result.requested()).isEqualTo(1);
        assertThat(result.succeeded()).isZero();
        assertThat(result.failed()).isEqualTo(1);
        assertThat(result.dramas()).isEmpty();
        assertThat(drama.getCoverUrl()).isEqualTo("/uploads/covers/old.jpg");
        verify(dramaRepository, never()).save(drama);
    }

    @Test
    void scheduledScanSkipsWhenPreviousRunIsStillActive() {
        BaiduPanClient baiduPanClient = mock(BaiduPanClient.class);
        DramaRepository dramaRepository = mock(DramaRepository.class);
        SystemConfigService configService = mock(SystemConfigService.class);
        BaiduAssetStorage assetStorage = mock(BaiduAssetStorage.class);
        SystemTaskService systemTaskService = mock(SystemTaskService.class);
        BaiduDramaScanner scanner = new BaiduDramaScanner(
                baiduPanClient,
                dramaRepository,
                configService,
                assetStorage,
                systemTaskService
        );
        AtomicInteger runs = new AtomicInteger();
        when(configService.get("baidu.scanEnabled")).thenReturn(Optional.of("true"));
        when(configService.get("baidu.scanRoot")).thenReturn(Optional.of("/root"));
        when(systemTaskService.run(
                any(SystemTaskType.class),
                any(),
                any(),
                any(),
                any(),
                any()
        )).thenAnswer(invocation -> {
            runs.incrementAndGet();
            scanner.scheduledScan();
            return List.of();
        });

        scanner.scheduledScan();

        assertThat(runs).hasValue(1);
    }

    private DramaEpisode episode(int episodeNo) {
        DramaEpisode episode = new DramaEpisode();
        episode.setEpisodeNo(episodeNo);
        episode.setSourcePath("/existing/%03d.mp4".formatted(episodeNo));
        return episode;
    }
}
