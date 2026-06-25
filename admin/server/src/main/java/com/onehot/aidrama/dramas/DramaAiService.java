package com.onehot.aidrama.dramas;

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
    private static final Pattern LEADING_INDEX = Pattern.compile("^\\d+[.．、\\s]*");
    private static final Pattern EPISODE_COUNT = Pattern.compile("[（(](\\d+)集[）)]");
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
        Drama drama = get(id);
        if (taskRepository.existsActiveByDramaId(id)) {
            throw new BusinessException("DRAMA_ALREADY_DISTRIBUTED", "这部剧已经分发过，不能重新生成 AI 剧名", HttpStatus.CONFLICT);
        }
        String systemPrompt = config("openai.prompts.dramaTitle", DEFAULT_TITLE_PROMPT);
        String userPrompt = titleContext(drama);
        String aiTitle = withAiErrors(() -> aiTaskService.run(
                textTask(AiTaskType.DRAMA_TITLE, drama, systemPrompt, userPrompt),
                () -> aiService.generateText(systemPrompt, userPrompt),
                result -> Map.of("outputText", result)
        ));
        drama.setAiTitle(cleanTitle(aiTitle));
        drama.setAiSummary(generateAiSummaryValue(drama));
        return repository.save(drama);
    }

    public Drama generateSummary(String id) {
        Drama drama = get(id);
        drama.setAiSummary(generateAiSummaryValue(drama));
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

    private String generateAiSummaryValue(Drama drama) {
        if (shouldUseSyntheticAiSummary(drama)) {
            return syntheticAiSummary(drama);
        }
        String systemPrompt = config("openai.prompts.dramaSummary", DEFAULT_SUMMARY_PROMPT);
        String userPrompt = summaryContext(drama);
        String aiSummary = withAiErrors(() -> aiTaskService.run(
                textTask(AiTaskType.DRAMA_SUMMARY, drama, systemPrompt, userPrompt),
                () -> aiService.generateText(systemPrompt, userPrompt),
                result -> Map.of("outputText", result)
        ));
        return cleanSummary(aiSummary, drama.getSummary(), drama.getTitle());
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
        int episodeCount = episodeCount(drama);
        if (episodeCount > 0) {
            return "%s（%d集）".formatted(title, episodeCount);
        }
        return title;
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

    private Drama get(String id) {
        return repository.findById(id)
                .orElseThrow(() -> new BusinessException("DRAMA_NOT_FOUND", "短剧不存在", HttpStatus.NOT_FOUND));
    }

    private String titleContext(Drama drama) {
        return """
                原始剧名：%s
                简介：%s
                """.formatted(
                blankToNone(drama.getTitle()),
                blankToNone(drama.getSummary())
        );
    }

    private String summaryContext(Drama drama) {
        return """
                原始剧名：%s
                AI剧名：%s
                原始简介：%s
                """.formatted(
                blankToNone(drama.getTitle()),
                blankToNone(drama.getAiTitle()),
                blankToNone(drama.getSummary())
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

    private String coverTitle(Drama drama) {
        if (drama.getAiTitle() != null && !drama.getAiTitle().isBlank()) {
            return drama.getAiTitle();
        }
        return blankToNone(drama.getTitle());
    }

    private String cleanTitle(String title) {
        return title.replace("《", "")
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
}
