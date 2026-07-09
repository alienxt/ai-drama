package com.onehot.aidrama.common.config;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.onehot.aidrama.categories.DramaCategory;
import com.onehot.aidrama.categories.DramaCategoryRepository;
import com.onehot.aidrama.configs.SystemConfigService;
import com.onehot.aidrama.dramas.DramaRatingBackfill;
import com.onehot.aidrama.users.AccountService;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

@Configuration
public class BootstrapConfig {
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final String OLD_DEFAULT_TITLE_PROMPT = """
            你是短剧发行增长编辑。根据原始剧名和简介，生成一个适合中文短剧分发平台的新剧名。
            要求：中文；不超过 12 个汉字；有爽点和情绪钩子；不要使用书名号；只输出剧名本身。
            """;
    private static final String DEFAULT_TITLE_PROMPT = """
            你是短剧发行增长编辑。根据原始剧名和简介，生成一个适合中文短剧分发平台的新剧名。
            要求：中文；不超过 12 个汉字；延续原始剧名的风格、意境和人物气质；在原有美感或情感基调上增强吸引力。
            不要把温柔、美感、情感向的原题改成血腥暴力、恐怖猎奇或过度复仇表达；避免使用灭门、血洗、屠、虐杀、杀疯、索命等词。
            可以更有悬念、更抓人，但不要偏离原题类型；不要使用书名号；只输出剧名本身。
            """;
    private static final String DEFAULT_SUMMARY_PROMPT = """
            你是短剧发行增长编辑。根据原始剧名、AI 剧名和原始简介，改写一个适合中文短剧分发平台的 AI 简介。
            要求：中文；不超过 100 个字符；最后三个字符必须是英文省略号 ...；不要脱离原简介的人物关系、剧情冲突和类型基调。
            写得更抓人、更有悬念，但不要编造原简介没有的核心设定；不要输出标题、引号、字段名或解释说明，只输出简介本身。
            """;
    private static final String OLD_DEFAULT_COVER_PROMPT = """
            你是短剧封面视觉总监。根据原始剧名、简介和原始封面信息，生成一张竖版中文短剧封面。
            画面要求：9:16 竖版海报；强剧情冲突；人物情绪明确；高点击率短剧风格；避免品牌水印和平台 Logo；画面中不要生成大段文字。
            """;
    private static final String OLD_DEFAULT_COVER_PROMPT_WITH_ORIGINAL_TITLE = """
            你是短剧封面视觉总监。根据封面剧名、原始剧名、简介和原始封面信息，生成一张竖版中文短剧封面。
            画面要求：9:16 竖版海报；保持美感和人物吸引力；人物好看、有情绪、有关系张力；氛围精致，有悬念和看点，让用户看了想点进内容。
            封面中要出现“封面剧名”的中文标题，标题清晰醒目但不要生成大段文字；优先表现情感、误会、重逢、身份反转等戏剧钩子。
            不要出现血腥、暴力、伤口、血迹、刀枪、尸体、恐怖猎奇或过度复仇画面；避免品牌水印和平台 Logo。
            """;
    private static final String DEFAULT_COVER_PROMPT = """
            你是短剧封面视觉总监。根据封面剧名、简介和原始封面信息，生成一张竖版中文短剧封面。
            画面要求：9:16 竖版海报；保持美感和人物吸引力；人物好看、有情绪、有关系张力；氛围精致，有悬念和看点，让用户看了想点进内容。
            封面中要出现“封面剧名”的中文标题，标题清晰醒目但不要生成大段文字；优先表现情感、误会、重逢、身份反转等戏剧钩子。
            画面文字只能出现“封面剧名”，不要出现原始剧名、旧标题、副标题或其他额外文字。
            不要出现血腥、暴力、伤口、血迹、刀枪、尸体、恐怖猎奇或过度复仇画面；避免品牌水印和平台 Logo。
            """;
    private static final String DEFAULT_METADATA_PROMPT = """
            你是短剧发行增长编辑。根据原始剧名和简介，一次生成中文与英文分发素材。
            输出严格 JSON 对象，不要 Markdown，不要解释，字段必须为 aiTitle、aiSummary、aiTitleEn、aiSummaryEn。
            aiTitle：中文短剧新剧名，不超过 12 个汉字；延续原始剧名风格、人物气质和类型基调；不要使用书名号。
            aiSummary：中文短剧简介，不超过 100 个字符，最后三个字符必须是英文省略号 ...；不要编造原简介没有的核心设定。
            aiTitleEn：适合 TikTok 的英文短剧标题，2-8 个英文单词，像剧集标题，不要使用引号。
            aiSummaryEn：适合 TikTok 的英文简介，不超过 160 个英文字符，突出人物关系、反转和悬念，不要编造原简介没有的核心设定。
            不要把温柔、美感、情感向的原题改成血腥暴力、恐怖猎奇或过度复仇表达；避免使用灭门、血洗、屠、虐杀、杀疯、索命等词。
            """;
    private static final String DEFAULT_VIDEO_COVER_PROMPT = """
            你是短剧视频封面视觉总监。根据封面剧名、简介和原始封面信息，生成一张横版中文短剧视频封面。
            画面要求：16:9 横版构图，适合 1280x720 视频首帧和视频缩略图；保持美感和人物吸引力；人物好看、有情绪、有关系张力；氛围精致，有悬念和看点，让用户看了想点进内容。
            封面中要出现“封面剧名”的中文标题，标题清晰醒目但不要生成大段文字；标题和人物不要贴边，避免被视频平台裁切。
            画面文字只能出现“封面剧名”，不要出现原始剧名、旧标题、副标题或其他额外文字。
            不要出现血腥、暴力、伤口、血迹、刀枪、尸体、恐怖猎奇或过度复仇画面；避免品牌水印和平台 Logo。
            """;

    @Bean
    CommandLineRunner bootstrapAdmin(
            AccountService accountService,
            SystemConfigService configService,
            DramaCategoryRepository categoryRepository,
            DramaRatingBackfill dramaRatingBackfill,
            @Value("${aidrama.bootstrap.admin-username}") String username,
            @Value("${aidrama.bootstrap.admin-password}") String password
    ) {
        return args -> {
            accountService.bootstrapAdmin(username, password);
            bootstrapBaiduConfig(configService);
            bootstrapHongguoConfig(configService);
            bootstrapOpenAiConfig(configService);
            bootstrapSystemTaskConfig(configService);
            bootstrapCategories(categoryRepository);
            dramaRatingBackfill.backfillMissingRatings();
        };
    }

    private void bootstrapSystemTaskConfig(SystemConfigService configService) {
        configService.putIfAbsent("system.taskTimeoutMs", "1800000", false);
        configService.putIfAbsent("drama.prepareOnDemandOnly", "true", false);
    }

    private void bootstrapBaiduConfig(SystemConfigService configService) throws Exception {
        Path configPath = Path.of("docs/baiduyun/baidu_pan_cli_config.json");
        if (Files.exists(configPath)) {
            Map<String, Object> config = MAPPER.readValue(Files.readString(configPath), new TypeReference<>() {
            });
            put(configService, "baidu.clientId", config.get("client_id"), false);
            put(configService, "baidu.clientSecret", config.get("client_secret"), true);
            put(configService, "baidu.accessToken", config.get("access_token"), true);
            put(configService, "baidu.refreshToken", config.get("refresh_token"), true);
            put(configService, "baidu.expiresIn", config.get("expires_in"), false);
            put(configService, "baidu.tokenObtainedAt", config.get("token_obtained_at"), false);
        }
        configService.putIfAbsent("baidu.scanRoot", "/drama/真人剧/2026", false);
        configService.putIfAbsent("baidu.scanEnabled", "true", false);
        configService.putIfAbsent("baidu.scanFixedDelayMs", "600000", false);
        configService.putIfAbsent("baidu.scanDownloadAssets", "true", false);
        configService.putIfAbsent("baidu.prepareFailureCooldownMs", "600000", false);
        configService.putIfAbsent("baidu.proxyEnabled", "false", false);
        configService.putIfAbsent("baidu.proxyHost", "", false);
        configService.putIfAbsent("baidu.proxyPort", "", false);
        configService.putIfAbsent("baidu.proxyUsername", "", false);
        configService.putIfAbsent("baidu.proxyPassword", "", true);
    }

    private void bootstrapHongguoConfig(SystemConfigService configService) {
        configService.putIfAbsent("hongguo.baseUrl", "https://www.52api.cn/api", false);
        configService.putIfAbsent("hongguo.apiKey", "", true);
        configService.putIfAbsent("hongguo.secretKey", "", true);
        configService.putIfAbsent("hongguo.connectTimeoutSeconds", "30", false);
        configService.putIfAbsent("hongguo.readTimeoutSeconds", "120", false);
        configService.putIfAbsent("hongguo.aiMangaAutoImportEnabled", "true", false);
        configService.putIfAbsent("hongguo.aiMangaAutoImportDailyLimit", "30", false);
        configService.putIfAbsent("hongguo.aiMangaAutoImportMaxPages", "8", false);
    }

    private void bootstrapOpenAiConfig(SystemConfigService configService) {
        configService.putIfAbsent("openai.baseUrl", "https://api.openai.com/v1", false);
        configService.putIfAbsent("openai.apiKey", "", true);
        configService.putIfAbsent("openai.textModel", "gpt-5.5", false);
        configService.putIfAbsent("openai.imageModel", "gpt-image-2", false);
        configService.putIfAbsent("openai.imageSize", "1024x1536", false);
        configService.putIfAbsent("openai.videoCoverImageSize", "1536x1024", false);
        configService.putIfAbsent("openai.imageQuality", "medium", false);
        configService.putIfAbsent("openai.imageOutputFormat", "jpeg", false);
        configService.putIfAbsent("openai.connectTimeoutSeconds", "30", false);
        configService.putIfAbsent("openai.readTimeoutSeconds", "300", false);
        putDefaultTitlePrompt(configService);
        putDefaultSummaryPrompt(configService);
        putDefaultMetadataPrompt(configService);
        putDefaultCoverPrompt(configService);
        putDefaultVideoCoverPrompt(configService);
    }

    private void putDefaultTitlePrompt(SystemConfigService configService) {
        String key = "openai.prompts.dramaTitle";
        String current = configService.get(key).orElse(null);
        if (current == null || current.equals(OLD_DEFAULT_TITLE_PROMPT)) {
            configService.put(key, DEFAULT_TITLE_PROMPT, false);
        }
    }

    private void putDefaultSummaryPrompt(SystemConfigService configService) {
        configService.putIfAbsent("openai.prompts.dramaSummary", DEFAULT_SUMMARY_PROMPT, false);
    }

    private void putDefaultMetadataPrompt(SystemConfigService configService) {
        configService.putIfAbsent("openai.prompts.dramaMetadata", DEFAULT_METADATA_PROMPT, false);
    }

    private void putDefaultCoverPrompt(SystemConfigService configService) {
        String key = "openai.prompts.dramaCover";
        String current = configService.get(key).orElse(null);
        if (current == null
                || current.equals(OLD_DEFAULT_COVER_PROMPT)
                || current.equals(OLD_DEFAULT_COVER_PROMPT_WITH_ORIGINAL_TITLE)) {
            configService.put(key, DEFAULT_COVER_PROMPT, false);
        }
    }

    private void putDefaultVideoCoverPrompt(SystemConfigService configService) {
        configService.putIfAbsent("openai.prompts.dramaVideoCover", DEFAULT_VIDEO_COVER_PROMPT, false);
    }

    private void put(SystemConfigService configService, String key, Object value, boolean secret) {
        if (value != null) {
            configService.putIfAbsent(key, String.valueOf(value), secret);
        }
    }

    private void bootstrapCategories(DramaCategoryRepository repository) {
        List<SeedCategory> categories = List.of(
                new SeedCategory("general", "通用", 10),
                new SeedCategory("urban", "都市", 20),
                new SeedCategory("romance", "甜宠情感", 30),
                new SeedCategory("counterattack", "逆袭爽剧", 40),
                new SeedCategory("miracle-doctor", "神医", 50),
                new SeedCategory("costume", "古装穿越", 60),
                new SeedCategory("food", "美食厨娘", 70),
                new SeedCategory("sci-fi", "科技系统", 80),
                new SeedCategory("suspense", "悬疑复仇", 90)
        );
        for (SeedCategory seed : categories) {
            repository.findByCode(seed.code()).orElseGet(() -> {
                DramaCategory category = new DramaCategory();
                category.setCode(seed.code());
                category.setName(seed.name());
                category.setSortOrder(seed.sortOrder());
                category.setEnabled(true);
                return repository.save(category);
            });
        }
    }

    private record SeedCategory(String code, String name, int sortOrder) {
    }
}
