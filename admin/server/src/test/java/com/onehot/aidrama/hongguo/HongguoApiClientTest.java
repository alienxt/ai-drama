package com.onehot.aidrama.hongguo;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.time.Instant;

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
    void formatChinaDateUsesShanghaiDate() {
        assertThat(HongguoApiClient.formatChinaDate(Instant.parse("2026-07-06T17:30:00Z")))
                .isEqualTo("2026-07-07");
    }

    @Test
    void formatChinaDateTimeUsesShanghaiTime() {
        assertThat(HongguoApiClient.formatChinaDateTime(Instant.parse("2026-07-07T07:00:00Z")))
                .isEqualTo("2026-07-07 15:00:00");
    }
}
