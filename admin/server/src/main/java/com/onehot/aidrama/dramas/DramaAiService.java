package com.onehot.aidrama.dramas;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.onehot.aidrama.ai.AiService;
import com.onehot.aidrama.ai.AiTask;
import com.onehot.aidrama.ai.AiTaskService;
import com.onehot.aidrama.ai.AiTaskType;
import com.onehot.aidrama.ai.OpenAiException;
import com.onehot.aidrama.common.error.BusinessException;
import com.onehot.aidrama.configs.SystemConfigService;
import com.onehot.aidrama.distribution.DistributionTaskRepository;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Service
public class DramaAiService {
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final Pattern LEADING_INDEX = Pattern.compile("^\\d+[.．、\\s]*");
    private static final Pattern EPISODE_COUNT = Pattern.compile("[（(](\\d+)集[）)]");
    private static final String DEFAULT_METADATA_PROMPT = """
            你是短剧发行增长编辑。根据原始剧名和简介，一次生成中文与英文分发素材。
            输出严格 JSON 对象，不要 Markdown，不要解释，字段必须为 aiTitle、aiSummary、aiTitleEn、aiSummaryEn。
            aiTitle：中文短剧新剧名，不超过 12 个汉字；延续原始剧名风格、人物气质和类型基调；不要使用书名号。
            aiSummary：中文短剧简介，不超过 100 个字符，最后三个字符必须是英文省略号 ...；不要编造原简介没有的核心设定。
            aiTitleEn：适合 TikTok 的英文短剧标题，2-8 个英文单词，像剧集标题，不要使用引号。
            aiSummaryEn：适合 TikTok 的英文简介，不超过 160 个英文字符，突出人物关系、反转和悬念，不要编造原简介没有的核心设定。
            不要把温柔、美感、情感向的原题改成血腥暴力、恐怖猎奇或过度复仇表达；避免使用灭门、血洗、屠、虐杀、杀疯、索命等词。
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
    private static final String DEFAULT_COVER_PROMPT = """
            你是短剧封面视觉总监。根据封面剧名、简介和原始封面信息，生成一张竖版中文短剧封面。
            画面要求：9:16 竖版海报；保持美感和人物吸引力；人物好看、有情绪、有关系张力；氛围精致，有悬念和看点，让用户看了想点进内容。
            封面中要出现“封面剧名”的中文标题，标题清晰醒目但不要生成大段文字；优先表现情感、误会、重逢、身份反转等戏剧钩子。
            画面文字只能出现“封面剧名”，不要出现原始剧名、旧标题、副标题或其他额外文字。
            不要出现血腥、暴力、伤口、血迹、刀枪、尸体、恐怖猎奇或过度复仇画面；避免品牌水印和平台 Logo。
            """;
    private static final String DEFAULT_VIDEO_COVER_PROMPT = """
            你是短剧视频封面视觉总监。根据封面剧名、简介和原始封面信息，生成一张横版中文短剧视频封面。
            画面要求：16:9 横版构图，适合 1280x720 视频首帧和视频缩略图；保持美感和人物吸引力；人物好看、有情绪、有关系张力；氛围精致，有悬念和看点，让用户看了想点进内容。
            封面中要出现“封面剧名”的中文标题，标题清晰醒目但不要生成大段文字；标题和人物不要贴边，避免被视频平台裁切。
            画面文字只能出现“封面剧名”，不要出现原始剧名、旧标题、副标题或其他额外文字。
            不要出现血腥、暴力、伤口、血迹、刀枪、尸体、恐怖猎奇或过度复仇画面；避免品牌水印和平台 Logo。
            """;
    private static final String DEFAULT_COVER_EN_PROMPT = """
            你是 TikTok 短剧封面视觉总监。根据英文封面剧名、简介和参考封面信息，生成一张竖版英文短剧封面。
            画面要求：9:16 竖版海报；适合 TikTok Drama；保持人物吸引力、情绪张力和戏剧悬念。
            封面中只能出现“英文封面剧名”的英文标题，标题清晰醒目但不要生成大段文字；不要出现中文、原始剧名、旧标题、副标题或其他额外文字。
            如果参考封面里有中文剧名，请理解为需要把中文剧名替换成英文封面剧名，而不是保留中文。
            不要出现血腥、暴力、伤口、血迹、刀枪、尸体、恐怖猎奇或过度复仇画面；避免品牌水印和平台 Logo。
            """;
    private static final String DEFAULT_VIDEO_COVER_EN_PROMPT = """
            你是 TikTok 短剧视频封面视觉总监。根据英文封面剧名、简介和参考封面信息，生成一张横版英文短剧视频封面。
            画面要求：16:9 横版构图，适合 1280x720 视频首帧和视频缩略图；保持人物吸引力、情绪张力和戏剧悬念。
            封面中只能出现“英文封面剧名”的英文标题，标题和人物不要贴边，避免被视频平台裁切；不要出现中文、原始剧名、旧标题、副标题或其他额外文字。
            如果参考封面里有中文剧名，请理解为需要把中文剧名替换成英文封面剧名，而不是保留中文。
            不要出现血腥、暴力、伤口、血迹、刀枪、尸体、恐怖猎奇或过度复仇画面；避免品牌水印和平台 Logo。
            """;

    private final DramaRepository repository;
    private final AiService aiService;
    private final DramaAiCoverStorage coverStorage;
    private final SystemConfigService configService;
    private final DistributionTaskRepository taskRepository;
    private final AiTaskService aiTaskService;

    public DramaAiService(
            DramaRepository repository,
            AiService aiService,
            DramaAiCoverStorage coverStorage,
            SystemConfigService configService,
            DistributionTaskRepository taskRepository,
            AiTaskService aiTaskService
    ) {
        this.repository = repository;
        this.aiService = aiService;
        this.coverStorage = coverStorage;
        this.configService = configService;
        this.taskRepository = taskRepository;
        this.aiTaskService = aiTaskService;
    }

    public Drama generateTitle(String id) {
        return generateTitle(id, false);
    }

    public Drama generateTitleForDistribution(String id) {
        return generateTitle(id, true);
    }

    private Drama generateTitle(String id, boolean allowActiveDistributionTask) {
        Drama drama = get(id);
        if (!allowActiveDistributionTask && taskRepository.existsActiveByDramaId(id)) {
            throw new BusinessException("DRAMA_ALREADY_DISTRIBUTED", "这部剧已经分发过，不能重新生成 AI 剧名", HttpStatus.CONFLICT);
        }
        AiMetadata metadata = generateAiMetadataValue(drama);
        applyMetadata(drama, metadata, true);
        return repository.save(drama);
    }

    public Drama generateSummary(String id) {
        Drama drama = get(id);
        AiMetadata metadata = generateAiMetadataValue(drama);
        applyMetadata(drama, metadata, false);
        return repository.save(drama);
    }

    public Drama generateCover(String id) {
        Drama drama = get(id);
        String coverPrompt = config("openai.prompts.dramaCover", DEFAULT_COVER_PROMPT) + "\n\n" + coverContext(drama);
        String videoCoverPrompt = config("openai.prompts.dramaVideoCover", DEFAULT_VIDEO_COVER_PROMPT) + "\n\n" + videoCoverContext(drama);
        return withAiErrors(() -> {
            if (trimToEmpty(drama.getAiCoverUrl()).isBlank()) {
                final String coverImageBase64 = aiTaskService.run(
                        imageTask(AiTaskType.DRAMA_COVER, drama, coverPrompt, aiService.imageSize()),
                        () -> aiService.generateImageBase64(coverPrompt, aiService.imageSize()),
                        result -> Map.of(
                                "outputFormat", aiService.imageOutputFormat(),
                                "size", aiService.imageSize()
                        )
                );
                return aiTaskService.run(
                        imageTask(AiTaskType.DRAMA_VIDEO_COVER, drama, videoCoverPrompt, aiService.videoCoverImageSize()),
                        () -> saveCoverResult(
                                drama,
                                coverImageBase64,
                                aiService.generateImageBase64(videoCoverPrompt, aiService.videoCoverImageSize())
                        ),
                        result -> mapOf(
                                "aiCoverUrl", result.getAiCoverUrl(),
                                "aiVideoCoverUrl", result.getAiVideoCoverUrl(),
                                "size", aiService.videoCoverImageSize(),
                                "outputFormat", aiService.imageOutputFormat()
                        )
                );
            }
            return aiTaskService.run(
                    imageTask(AiTaskType.DRAMA_VIDEO_COVER, drama, videoCoverPrompt, aiService.videoCoverImageSize()),
                    () -> saveCoverResult(
                            drama,
                            null,
                            aiService.generateImageBase64(videoCoverPrompt, aiService.videoCoverImageSize())
                    ),
                    result -> mapOf(
                            "aiCoverUrl", result.getAiCoverUrl(),
                            "aiVideoCoverUrl", result.getAiVideoCoverUrl(),
                            "size", aiService.videoCoverImageSize(),
                            "outputFormat", aiService.imageOutputFormat()
                    )
            );
        });
    }

    public Drama generateEnglishCover(String id) {
        Drama drama = get(id);
        String coverPrompt = config("openai.prompts.dramaCoverEn", DEFAULT_COVER_EN_PROMPT) + "\n\n" + englishCoverContext(drama);
        String videoCoverPrompt = config("openai.prompts.dramaVideoCoverEn", DEFAULT_VIDEO_COVER_EN_PROMPT) + "\n\n" + englishVideoCoverContext(drama);
        return withAiErrors(() -> {
            String coverImageBase64 = null;
            if (trimToEmpty(drama.getAiCoverEnUrl()).isBlank()) {
                coverImageBase64 = aiTaskService.run(
                        imageTask(AiTaskType.DRAMA_COVER_EN, drama, coverPrompt, aiService.imageSize()),
                        () -> aiService.generateImageBase64(coverPrompt, aiService.imageSize()),
                        result -> Map.of(
                                "outputFormat", aiService.imageOutputFormat(),
                                "size", aiService.imageSize()
                        )
                );
            }
            if (trimToEmpty(drama.getAiVideoCoverEnUrl()).isBlank()) {
                final String finalCoverImageBase64 = coverImageBase64;
                return aiTaskService.run(
                        imageTask(AiTaskType.DRAMA_VIDEO_COVER_EN, drama, videoCoverPrompt, aiService.videoCoverImageSize()),
                        () -> saveEnglishCoverResult(
                                drama,
                                finalCoverImageBase64,
                                aiService.generateImageBase64(videoCoverPrompt, aiService.videoCoverImageSize())
                        ),
                        result -> mapOf(
                                "aiCoverEnUrl", result.getAiCoverEnUrl(),
                                "aiVideoCoverEnUrl", result.getAiVideoCoverEnUrl(),
                                "size", aiService.videoCoverImageSize(),
                                "outputFormat", aiService.imageOutputFormat()
                        )
                );
            }
            if (coverImageBase64 != null) {
                return saveEnglishCoverResult(drama, coverImageBase64, null);
            }
            return drama;
        });
    }

    private AiMetadata generateAiMetadataValue(Drama drama) {
        String systemPrompt = config("openai.prompts.dramaMetadata", DEFAULT_METADATA_PROMPT);
        String userPrompt = metadataContext(drama);
        String output = withAiErrors(() -> aiTaskService.run(
                textTask(AiTaskType.DRAMA_METADATA, drama, systemPrompt, userPrompt),
                () -> aiService.generateText(systemPrompt, userPrompt),
                result -> Map.of("outputText", result)
        ));
        return cleanMetadata(parseMetadata(output), drama);
    }

    private void applyMetadata(Drama drama, AiMetadata metadata, boolean updateTitle) {
        if (updateTitle || trimToEmpty(drama.getAiTitle()).isBlank()) {
            drama.setAiTitle(metadata.aiTitle());
        }
        drama.setAiTitleEn(metadata.aiTitleEn());
        drama.setAiSummary(metadata.aiSummary());
        drama.setAiSummaryEn(metadata.aiSummaryEn());
    }

    private AiMetadata parseMetadata(String output) {
        String text = trimToEmpty(output);
        if (text.isBlank()) {
            return new AiMetadata(null, null, null, null);
        }
        try {
            JsonNode node = MAPPER.readTree(extractJson(text));
            return new AiMetadata(
                    text(node, "aiTitle", "title", "titleZh", "zhTitle"),
                    text(node, "aiSummary", "summary", "summaryZh", "zhSummary"),
                    text(node, "aiTitleEn", "titleEn", "enTitle", "englishTitle"),
                    text(node, "aiSummaryEn", "summaryEn", "enSummary", "englishSummary")
            );
        } catch (Exception ignored) {
            return new AiMetadata(text, null, null, null);
        }
    }

    private AiMetadata cleanMetadata(AiMetadata metadata, Drama drama) {
        String aiTitle = cleanTitle(firstText(metadata.aiTitle(), drama.getAiTitle(), drama.getTitle()));
        String fallbackSummary = shouldUseSyntheticAiSummary(drama) ? syntheticAiSummaryWithTitle(drama, aiTitle) : null;
        String aiSummary = cleanSummary(
                firstText(metadata.aiSummary(), fallbackSummary),
                drama.getSummary(),
                firstText(aiTitle, drama.getTitle())
        );
        String aiTitleEn = cleanEnglishTitle(metadata.aiTitleEn());
        String aiSummaryEn = cleanEnglishSummary(metadata.aiSummaryEn(), aiTitleEn);
        return new AiMetadata(aiTitle, aiSummary, aiTitleEn, aiSummaryEn);
    }

    private String extractJson(String text) {
        String trimmed = text.trim();
        if (trimmed.startsWith("```")) {
            trimmed = trimmed.replaceFirst("^```[a-zA-Z]*\\s*", "")
                    .replaceFirst("\\s*```$", "")
                    .trim();
        }
        int start = trimmed.indexOf('{');
        int end = trimmed.lastIndexOf('}');
        if (start >= 0 && end > start) {
            return trimmed.substring(start, end + 1);
        }
        return trimmed;
    }

    private String text(JsonNode node, String... fields) {
        for (String field : fields) {
            JsonNode value = node.path(field);
            if (!value.isMissingNode() && !value.isNull()) {
                String text = value.asText(null);
                if (text != null && !text.isBlank()) {
                    return text.trim();
                }
            }
        }
        return null;
    }

    private boolean shouldUseSyntheticAiSummary(Drama drama) {
        String summary = trimToEmpty(drama.getSummary());
        if (summary.isBlank()) {
            return true;
        }
        String title = trimToEmpty(drama.getTitle());
        if (!title.isBlank() && summary.equals(title)) {
            return true;
        }
        String sourceName = sourceName(drama.getSourcePath());
        if (!sourceName.isBlank() && summary.equals(sourceName)) {
            return true;
        }
        return !title.isBlank() && summary.matches(Pattern.quote(title) + "\\s*[（(]\\d+集[）)].*");
    }

    private String syntheticAiSummary(Drama drama) {
        String title = trimToEmpty(drama.getAiTitle());
        if (title.isBlank()) {
            title = trimToEmpty(drama.getTitle());
        }
        return syntheticAiSummaryWithTitle(drama, title);
    }

    private String syntheticAiSummaryWithTitle(Drama drama, String title) {
        String effectiveTitle = trimToEmpty(title);
        if (effectiveTitle.isBlank()) {
            effectiveTitle = trimToEmpty(drama.getTitle());
        }
        int episodeCount = episodeCount(drama);
        if (episodeCount > 0) {
            return "%s（%d集）".formatted(effectiveTitle, episodeCount);
        }
        return effectiveTitle;
    }

    private int episodeCount(Drama drama) {
        List<DramaEpisode> episodes = drama.getEpisodes();
        if (episodes != null && !episodes.isEmpty()) {
            return episodes.size();
        }
        return parseEpisodeCount(drama.getSummary(), drama.getSourcePath(), drama.getTitle());
    }

    private int parseEpisodeCount(String... values) {
        for (String value : values) {
            Matcher matcher = EPISODE_COUNT.matcher(trimToEmpty(value));
            if (matcher.find()) {
                return Integer.parseInt(matcher.group(1));
            }
        }
        return 0;
    }

    private String sourceName(String sourcePath) {
        String value = trimToEmpty(sourcePath);
        int slash = value.lastIndexOf('/');
        if (slash >= 0) {
            value = value.substring(slash + 1);
        }
        return LEADING_INDEX.matcher(value).replaceFirst("").trim();
    }

    private AiTask textTask(AiTaskType type, Drama drama, String systemPrompt, String userPrompt) {
        AiTask task = baseTask(type, drama);
        task.setModel(aiService.textModel());
        task.setEndpoint("/responses");
        task.setPrompt(systemPrompt + "\n\n" + userPrompt);
        task.setRequestPayload(mapOf(
                "model", aiService.textModel(),
                "instructions", systemPrompt,
                "input", userPrompt,
                "text", Map.of("verbosity", "low")
        ));
        return task;
    }

    private AiTask imageTask(AiTaskType type, Drama drama, String prompt, String size) {
        AiTask task = baseTask(type, drama);
        task.setModel(aiService.imageModel());
        task.setEndpoint("/images/generations");
        task.setPrompt(prompt);
        task.setRequestPayload(mapOf(
                "model", aiService.imageModel(),
                "prompt", prompt,
                "n", 1,
                "size", size,
                "quality", aiService.imageQuality(),
                "output_format", aiService.imageOutputFormat()
        ));
        return task;
    }

    private AiTask baseTask(AiTaskType type, Drama drama) {
        AiTask task = new AiTask();
        task.setType(type);
        task.setSubjectType("DRAMA");
        task.setSubjectId(drama.getId());
        return task;
    }

    private Map<String, Object> mapOf(Object... pairs) {
        Map<String, Object> values = new LinkedHashMap<>();
        for (int index = 0; index < pairs.length; index += 2) {
            values.put(String.valueOf(pairs[index]), pairs[index + 1]);
        }
        return values;
    }

    private Drama saveCoverResult(Drama drama, String coverImageBase64, String videoCoverImageBase64) {
        String outputFormat = aiService.imageOutputFormat();
        if (coverImageBase64 != null && !coverImageBase64.isBlank()) {
            drama.setAiCoverUrl(coverStorage.store(coverImageBase64, outputFormat));
        }
        drama.setAiVideoCoverUrl(coverStorage.store(videoCoverImageBase64, outputFormat));
        drama.setAiCoverGenerating(false);
        return repository.save(drama);
    }

    private Drama saveEnglishCoverResult(Drama drama, String coverImageBase64, String videoCoverImageBase64) {
        String outputFormat = aiService.imageOutputFormat();
        if (coverImageBase64 != null && !coverImageBase64.isBlank()) {
            drama.setAiCoverEnUrl(coverStorage.store(coverImageBase64, outputFormat));
        }
        if (videoCoverImageBase64 != null && !videoCoverImageBase64.isBlank()) {
            drama.setAiVideoCoverEnUrl(coverStorage.store(videoCoverImageBase64, outputFormat));
        }
        drama.setAiCoverGenerating(false);
        return repository.save(drama);
    }

    private Drama get(String id) {
        return repository.findById(id)
                .orElseThrow(() -> new BusinessException("DRAMA_NOT_FOUND", "短剧不存在", HttpStatus.NOT_FOUND));
    }

    private String metadataContext(Drama drama) {
        return """
                原始剧名：%s
                当前AI剧名：%s
                原始简介：%s
                集数：%s
                """.formatted(
                blankToNone(drama.getTitle()),
                blankToNone(drama.getAiTitle()),
                blankToNone(drama.getSummary()),
                episodeCount(drama) > 0 ? episodeCount(drama) + "集" : "未知"
        );
    }

    private String coverContext(Drama drama) {
        return """
                封面剧名：%s
                简介：%s
                原始封面：%s
                """.formatted(
                coverTitle(drama),
                blankToNone(drama.getSummary()),
                blankToNone(drama.getCoverUrl())
        );
    }

    private String videoCoverContext(Drama drama) {
        return coverContext(drama) + "\n视频目标：横版视频首帧和缩略图，最终会用于 1280x720 横屏视频。";
    }

    private String englishCoverContext(Drama drama) {
        return """
                英文封面剧名：%s
                英文简介：%s
                中文AI剧名：%s
                中文简介：%s
                参考封面：%s
                中文AI封面：%s
                """.formatted(
                englishCoverTitle(drama),
                blankToNone(firstText(drama.getAiSummaryEn(), drama.getAiSummary(), drama.getSummary())),
                blankToNone(drama.getAiTitle()),
                blankToNone(firstText(drama.getAiSummary(), drama.getSummary())),
                blankToNone(firstText(drama.getAiCoverUrl(), drama.getCoverUrl())),
                blankToNone(drama.getAiCoverUrl())
        );
    }

    private String englishVideoCoverContext(Drama drama) {
        return englishCoverContext(drama) + "\n视频目标：横版视频首帧和缩略图，最终会用于 1280x720 横屏视频。";
    }

    private String coverTitle(Drama drama) {
        if (drama.getAiTitle() != null && !drama.getAiTitle().isBlank()) {
            return drama.getAiTitle();
        }
        return blankToNone(drama.getTitle());
    }

    private String englishCoverTitle(Drama drama) {
        return blankToNone(firstText(drama.getAiTitleEn(), drama.getAiTitle(), drama.getTitle()));
    }

    private String cleanTitle(String title) {
        return trimToEmpty(title)
                .replace("《", "")
                .replace("》", "")
                .replace("\"", "")
                .replace("'", "")
                .trim();
    }

    private String cleanSummary(String summary, String fallbackSummary, String fallbackTitle) {
        String text = summary == null ? "" : summary;
        text = text.replace("《", "")
                .replace("》", "")
                .replace("\"", "")
                .replace("'", "")
                .replace("…", "...")
                .replaceAll("[\\r\\n\\t]+", " ")
                .replaceAll("\\s+", " ")
                .trim();
        if (text.isBlank()) {
            text = fallbackSummary == null || fallbackSummary.isBlank()
                    ? "围绕%s展开人物命运与情感反转".formatted(blankToNone(fallbackTitle))
                    : fallbackSummary.trim();
        }
        text = text.replaceAll("(?:\\.\\.\\.)+$", "")
                .replaceAll("[。！？!?,，、；;：:\\s]+$", "")
                .trim();
        if (text.length() > 97) {
            text = text.substring(0, 97).replaceAll("[。！？!?,，、；;：:\\s]+$", "");
        }
        if (text.isBlank()) {
            text = "人物命运翻转，情感与悬念层层推进";
        }
        return text + "...";
    }

    private String cleanEnglishTitle(String title) {
        String text = trimToEmpty(title)
                .replace("《", "")
                .replace("》", "")
                .replace("\"", "")
                .replace("'", "")
                .replaceAll("[\\r\\n\\t]+", " ")
                .replaceAll("\\s+", " ")
                .trim();
        if (text.length() > 80) {
            text = text.substring(0, 80).replaceAll("[\\s,.;:!?-]+$", "");
        }
        return text.isBlank() ? null : text;
    }

    private String cleanEnglishSummary(String summary, String fallbackTitle) {
        String text = trimToEmpty(summary)
                .replace("《", "")
                .replace("》", "")
                .replace("\"", "")
                .replaceAll("[\\r\\n\\t]+", " ")
                .replaceAll("\\s+", " ")
                .trim();
        if (text.isBlank() && fallbackTitle != null && !fallbackTitle.isBlank()) {
            text = "%s hides secrets, reversals, and emotional stakes in a fast-paced short drama.".formatted(fallbackTitle);
        }
        if (text.length() > 160) {
            text = text.substring(0, 160).replaceAll("[\\s,.;:!?-]+$", "");
        }
        return text.isBlank() ? null : text;
    }

    private String firstText(String... values) {
        for (String value : values) {
            if (value != null && !value.isBlank()) {
                return value.trim();
            }
        }
        return null;
    }

    private String blankToNone(String value) {
        return value == null || value.isBlank() ? "无" : value;
    }

    private String trimToEmpty(String value) {
        return value == null ? "" : value.trim();
    }

    private String config(String key, String defaultValue) {
        return configService.get(key).filter(value -> !value.isBlank()).orElse(defaultValue);
    }

    private <T> T withAiErrors(AiCall<T> call) {
        try {
            return call.execute();
        } catch (OpenAiException | IllegalStateException exception) {
            throw new BusinessException("OPENAI_ERROR", exception.getMessage(), HttpStatus.BAD_GATEWAY);
        }
    }

    private interface AiCall<T> {
        T execute();
    }

    private record AiMetadata(String aiTitle, String aiSummary, String aiTitleEn, String aiSummaryEn) {
    }
}
