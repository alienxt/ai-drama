package com.onehot.aidrama.hongguo;

import java.util.Arrays;
import java.util.List;

public enum OtherShortDramaChannel {
    HEMA("HEMA", "河马短剧", "/hm_duanju", Mode.SEARCH, "search", "detail", "video", null, "keyword", "id", "穿越"),
    XIFAN("XIFAN", "喜番短剧", "/xifan", Mode.SEARCH, "search", "detail", null, null, "keyword", "id", "穿越"),
    XIFAN_TOP("XIFAN_TOP", "喜番短剧排行榜", "/xifan_top", Mode.RANK, "top", "list", null, "XIFAN", "id", "id", null),
    HUOLONG("HUOLONG", "火龙漫剧", "/huolong", Mode.SEARCH, "search", "detail", "video", null, "keyword", "id", "漫剧"),
    HUOLONG_TOP("HUOLONG_TOP", "火龙漫剧排行榜", "/huolong_top", Mode.RANK, "top", "list", null, "HUOLONG", "id", "id", null),
    DONGLI("DONGLI", "东梨短剧", "/dongli", Mode.SEARCH, "search", "detail", null, null, "keyword", "id", "穿越"),
    DONGLI_TOP("DONGLI_TOP", "东梨短剧排行榜", "/dongli_top", Mode.RANK, "top", "list", null, "DONGLI", "id", "id", null),
    XINGYA("XINGYA", "星芽短剧", "/xingya", Mode.SEARCH, "search", "detail", null, null, "keyword", "id", "穿越"),
    XINGYA_TOP("XINGYA_TOP", "星芽短剧排行榜", "/xingya_top", Mode.RANK, "top", "list", null, "XINGYA", "id", "id", null),
    WEIGUAN("WEIGUAN", "围观短剧", "/wg_duanju", Mode.SEARCH, "search", "detail", "video", null, "keyword", "id", "穿越"),
    DOUYIN("DOUYIN", "抖音短剧", "/douyin_duanju", Mode.CATEGORY, "series", "lists", "video", null, "content_id", "id", null),
    QIMAO("QIMAO", "七猫短剧", "/qm_duanju", Mode.SEARCH, "search", "info", null, null, "keyword", "id", "穿越"),
    QIMAO_TOP("QIMAO_TOP", "七猫短剧榜单", "/qm_top", Mode.RANK, "all", "list", null, "QIMAO", "tag_id", "tag_id", null),
    BAIDU("BAIDU", "百度短剧", "/bd_duanju", Mode.SEARCH, "search", "detail", "video", null, "keyword", "id", "穿越");

    private static final String PROVIDER_PREFIX = "52API_";

    private final String code;
    private final String label;
    private final String apiPath;
    private final Mode mode;
    private final String optionType;
    private final String listType;
    private final String videoType;
    private final String detailChannelCode;
    private final String listSelectorParam;
    private final String detailIdParam;
    private final String defaultKeyword;

    OtherShortDramaChannel(
            String code,
            String label,
            String apiPath,
            Mode mode,
            String optionType,
            String listType,
            String videoType,
            String detailChannelCode,
            String listSelectorParam,
            String detailIdParam,
            String defaultKeyword
    ) {
        this.code = code;
        this.label = label;
        this.apiPath = apiPath;
        this.mode = mode;
        this.optionType = optionType;
        this.listType = listType;
        this.videoType = videoType;
        this.detailChannelCode = detailChannelCode;
        this.listSelectorParam = listSelectorParam;
        this.detailIdParam = detailIdParam;
        this.defaultKeyword = defaultKeyword;
    }

    public String code() {
        return code;
    }

    public String label() {
        return label;
    }

    public String apiPath() {
        return apiPath;
    }

    public Mode mode() {
        return mode;
    }

    public String optionType() {
        return optionType;
    }

    public String listType() {
        return listType;
    }

    public String videoType() {
        return videoType;
    }

    public String listSelectorParam() {
        return listSelectorParam;
    }

    public String detailIdParam() {
        return detailIdParam;
    }

    public String defaultKeyword() {
        return defaultKeyword == null ? "" : defaultKeyword;
    }

    public boolean needsOption() {
        return mode == Mode.RANK || mode == Mode.CATEGORY;
    }

    public boolean supportsKeyword() {
        return mode == Mode.SEARCH;
    }

    public boolean supportsVideo() {
        return videoType != null && !videoType.isBlank();
    }

    public String providerCode() {
        return PROVIDER_PREFIX + detailChannel().code;
    }

    public OtherShortDramaChannel detailChannel() {
        if (detailChannelCode == null || detailChannelCode.isBlank()) {
            return this;
        }
        return fromCode(detailChannelCode);
    }

    public static List<OtherShortDramaChannel> visibleChannels() {
        return Arrays.stream(values())
                .filter(channel -> channel != XIFAN)
                .filter(channel -> channel.mode != Mode.RANK || channel == XIFAN_TOP)
                .toList();
    }

    public static OtherShortDramaChannel fromCode(String code) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("Unsupported short drama channel: " + code);
        }
        return Arrays.stream(values())
                .filter(channel -> channel.code.equalsIgnoreCase(code.trim()))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("Unsupported short drama channel: " + code));
    }

    public static OtherShortDramaChannel fromProviderCode(String providerCode) {
        if (providerCode == null || providerCode.isBlank() || !providerCode.startsWith(PROVIDER_PREFIX)) {
            throw new IllegalArgumentException("Unsupported short drama provider: " + providerCode);
        }
        return fromCode(providerCode.substring(PROVIDER_PREFIX.length()));
    }

    public enum Mode {
        SEARCH,
        RANK,
        CATEGORY
    }
}
