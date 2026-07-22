package com.onehot.aidrama.hongguo;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Base64;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class HongguoApiClientTest {
    @Test
    void parseMangaSearchItemsReadsDirectDataArrayResponse() throws Exception {
        JsonNode data = new ObjectMapper().readTree("""
                [
                  {
                    "id": "7651185408138546201",
                    "title": "全民转职，我一个辅助全是禁咒？",
                    "desc": "本作是奇幻爽文动态漫",
                    "cover": "https://example.com/cover.jpg",
                    "duration_num": 5113,
                    "episode_num": 87,
                    "followed_num": 143830,
                    "create_time": "2026-07-05 10:20:30"
                  }
                ]
                """);
        HongguoApiClient client = new HongguoApiClient(null, null, null);

        var items = client.parseMangaSearchItems(data);

        assertThat(items).hasSize(1);
        HongguoApiModels.MangaSearchItem item = items.getFirst();
        assertThat(item.providerDramaId()).isEqualTo("7651185408138546201");
        assertThat(item.title()).isEqualTo("全民转职，我一个辅助全是禁咒？");
        assertThat(item.summary()).isEqualTo("本作是奇幻爽文动态漫");
        assertThat(item.coverUrl()).isEqualTo("https://example.com/cover.jpg");
        assertThat(item.episodeCount()).isEqualTo(87);
        assertThat(item.playCount()).isEqualTo(143830L);
        assertThat(item.publishedAt()).isNotNull();
    }

    @Test
    void parseMangaSearchItemsReadsScreeningListFields() throws Exception {
        JsonNode data = new ObjectMapper().readTree("""
                {
                  "session_id": "20260709100000ABC",
                  "lists": [
                    {
                      "id": "screen-1",
                      "title": "AI漫剧上新第一部",
                      "desc": "筛选接口返回的AI漫剧",
                      "cover": "https://example.com/screen.jpg",
                      "episodeNum": 42,
                      "playNum": 8888,
                      "copyright": "红果短剧",
                      "duration": "2小时4分钟",
                      "sub_title_list": ["新剧", "AI漫剧"],
                      "tag_info": {"new": "新剧"}
                    }
                  ]
                }
                """);
        HongguoApiClient client = new HongguoApiClient(null, null, null);

        var items = client.parseMangaSearchItems(data);

        assertThat(items).hasSize(1);
        HongguoApiModels.MangaSearchItem item = items.getFirst();
        assertThat(item.providerDramaId()).isEqualTo("screen-1");
        assertThat(item.title()).isEqualTo("AI漫剧上新第一部");
        assertThat(item.episodeCount()).isEqualTo(42);
        assertThat(item.playCount()).isEqualTo(8888L);
        assertThat(item.categories()).contains("新剧", "AI漫剧");
        assertThat(item.recTags()).contains("新剧");
    }

    @Test
    void parseMangaSearchItemsReadsNewTopListFields() throws Exception {
        JsonNode data = new ObjectMapper().readTree("""
                {
                  "lists": [
                    {
                      "id": "top-1",
                      "title": "AI剧新剧榜第一部",
                      "desc": "榜单接口返回的AI剧",
                      "cover": "https://example.com/top.jpg",
                      "score": "8.5",
                      "episode_num": 77,
                      "play_num": 994
                    }
                  ],
                  "type": "ai_playlet_new_rank"
                }
                """);
        HongguoApiClient client = new HongguoApiClient(null, null, null);

        var items = client.parseMangaSearchItems(data);

        assertThat(items).hasSize(1);
        HongguoApiModels.MangaSearchItem item = items.getFirst();
        assertThat(item.providerDramaId()).isEqualTo("top-1");
        assertThat(item.title()).isEqualTo("AI剧新剧榜第一部");
        assertThat(item.summary()).isEqualTo("榜单接口返回的AI剧");
        assertThat(item.coverUrl()).isEqualTo("https://example.com/top.jpg");
        assertThat(item.score()).isEqualTo("8.5");
        assertThat(item.episodeCount()).isEqualTo(77);
        assertThat(item.playCount()).isEqualTo(994L);
    }

    @Test
    void parseMangaSearchItemsReadsXifanTopListFields() throws Exception {
        JsonNode data = new ObjectMapper().readTree("""
                {
                  "lists": [
                    {
                      "id": "675524",
                      "name": "林厨携手创商业传奇",
                      "summary": "厨师林耀接手负债累累的老味饭店。",
                      "cover": "https://example.com/xifan.png",
                      "thumbnail": "https://example.com/xifan.webp",
                      "score": 6.3,
                      "episodeNum": 44
                    }
                  ]
                }
                """);
        HongguoApiClient client = new HongguoApiClient(null, null, null);

        var items = client.parseMangaSearchItems(data);

        assertThat(items).hasSize(1);
        HongguoApiModels.MangaSearchItem item = items.getFirst();
        assertThat(item.providerDramaId()).isEqualTo("675524");
        assertThat(item.title()).isEqualTo("林厨携手创商业传奇");
        assertThat(item.summary()).isEqualTo("厨师林耀接手负债累累的老味饭店。");
        assertThat(item.coverUrl()).isEqualTo("https://example.com/xifan.png");
        assertThat(item.score()).isEqualTo("6.3");
        assertThat(item.episodeCount()).isEqualTo(44);
    }

    @Test
    void formatChinaDateUsesShanghaiDate() {
        assertThat(HongguoApiClient.formatChinaDate(Instant.parse("2026-07-06T17:30:00Z")))
                .isEqualTo("2026-07-07");
    }

    @Test
    void formatChinaDateTimeUsesShanghaiTime() {
        assertThat(HongguoApiClient.formatChinaDateTime(Instant.parse("2026-07-07T07:00:00Z")))
                .isEqualTo("2026-07-07 15:00:00");
    }

    @Test
    void joinFilterIdsBase64EncodesLargeValues() throws Exception {
        HongguoApiClient client = new HongguoApiClient(null, null, null);
        List<String> ids = java.util.stream.IntStream.range(0, 180)
                .mapToObj(index -> "7651185408138546%04d".formatted(index))
                .toList();

        String encoded = joinFilterIds(client, ids);

        assertThat(encoded).doesNotContain(",");
        String decoded = new String(Base64.getDecoder().decode(encoded), StandardCharsets.UTF_8);
        assertThat(decoded).isEqualTo(String.join(",", ids));
    }

    @Test
    void parseVideoVariantsReadsDouyinNestedVideoUrlAndProviderVideoId() throws Exception {
        JsonNode data = new ObjectMapper().readTree("""
                {
                  "lists": [
                    {
                      "id": "episode-1",
                      "video": {
                        "duration": "2分钟50秒",
                        "width": 1080,
                        "height": 1920,
                        "url": "https://example.com/episode-1.mp4"
                      }
                    }
                  ]
                }
                """);
        HongguoApiClient client = new HongguoApiClient(null, null, null);

        var variants = parseVideoVariants(client, data, false);

        assertThat(variants).hasSize(1);
        HongguoApiModels.VideoVariant variant = variants.getFirst();
        assertThat(variant.providerVideoId()).isEqualTo("episode-1");
        assertThat(variant.url()).isEqualTo("https://example.com/episode-1.mp4");
        assertThat(variant.duration()).isEqualTo("2分钟50秒");
        assertThat(variant.width()).isEqualTo(1080);
        assertThat(variant.height()).isEqualTo(1920);
    }

    @Test
    void parseDramaDetailReadsDouyinNestedEpisodeDownloadUrl() throws Exception {
        JsonNode data = new ObjectMapper().readTree("""
                {
                  "lists": [
                    {
                      "id": "episode-1",
                      "name": "第 1 集",
                      "video": {
                        "url": "https://example.com/episode-1.mp4"
                      }
                    }
                  ]
                }
                """);
        HongguoApiClient client = new HongguoApiClient(null, null, null);

        var detail = parseDramaDetail(client, "drama-1", data);

        assertThat(detail.episodes()).hasSize(1);
        HongguoApiModels.DetailEpisode episode = detail.episodes().getFirst();
        assertThat(episode.providerVideoId()).isEqualTo("episode-1");
        assertThat(episode.downloadUrl()).isEqualTo("https://example.com/episode-1.mp4");
    }

    private String joinFilterIds(HongguoApiClient client, List<String> ids) throws Exception {
        Method method = HongguoApiClient.class.getDeclaredMethod("joinFilterIds", List.class);
        method.setAccessible(true);
        return (String) method.invoke(client, ids);
    }

    @SuppressWarnings("unchecked")
    private List<HongguoApiModels.VideoVariant> parseVideoVariants(
            HongguoApiClient client,
            JsonNode data,
            boolean requireDecryptKey
    ) throws Exception {
        Method method = HongguoApiClient.class.getDeclaredMethod("parseVideoVariants", JsonNode.class, boolean.class);
        method.setAccessible(true);
        return (List<HongguoApiModels.VideoVariant>) method.invoke(client, data, requireDecryptKey);
    }

    private HongguoApiModels.DramaDetail parseDramaDetail(
            HongguoApiClient client,
            String providerDramaId,
            JsonNode data
    ) throws Exception {
        Method method = HongguoApiClient.class.getDeclaredMethod("parseDramaDetail", String.class, JsonNode.class);
        method.setAccessible(true);
        return (HongguoApiModels.DramaDetail) method.invoke(client, providerDramaId, data);
    }
}
