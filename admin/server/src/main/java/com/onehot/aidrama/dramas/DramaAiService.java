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
import java.util.Map;

@Service
public class DramaAiService {
    private static final String DEFAULT_TITLE_PROMPT = """
            你是短剧发行增长编辑。根据原始剧名和简介，生成一个适合中文短剧分发平台的新剧名。
            要求：中文；不超过 12 个汉字；延续原始剧名的风格、意境和人物气质；在原有美感或情感基调上增强吸引力。
            不要把温柔、美感、情感向的原题改成血腥暴力、恐怖猎奇或过度复仇表达；避免使用灭门、血洗、屠、虐杀、杀疯、索命等词。
            可以更有悬念、更抓人，但不要偏离原题类型；不要使用书名号；只输出剧名本身。
            """;
    private static final String DEFAULT_COVER_PROMPT = """
            你是短剧封面视觉总监。根据封面剧名、简介和原始封面信息，生成一张竖版中文短剧封面。
            画面要求：9:16 竖版海报；保持美感和人物吸引力；人物好看、有情绪、有关系张力；氛围精致，有悬念和看点，让用户看了想点进内容。
            封面中要出现“封面剧名”的中文标题，标题清晰醒目但不要生成大段文字；优先表现情感、误会、重逢、身份反转等戏剧钩子。
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
        String userPrompt = dramaContext(drama);
        String aiTitle = withAiErrors(() -> aiTaskService.run(
                textTask(drama, systemPrompt, userPrompt),
                () -> aiService.generateText(systemPrompt, userPrompt),
                result -> Map.of("outputText", result)
        ));
        drama.setAiTitle(cleanTitle(aiTitle));
        return repository.save(drama);
    }

    public Drama generateCover(String id) {
        Drama drama = get(id);
        String prompt = config("openai.prompts.dramaCover", DEFAULT_COVER_PROMPT) + "\n\n" + coverContext(drama);
        return withAiErrors(() -> aiTaskService.run(
                imageTask(drama, prompt),
                () -> saveCoverResult(drama, aiService.generateImageBase64(prompt)),
                result -> mapOf(
                        "aiCoverUrl", result.getAiCoverUrl(),
                        "outputFormat", aiService.imageOutputFormat()
                )
        ));
    }

    private AiTask textTask(Drama drama, String systemPrompt, String userPrompt) {
        AiTask task = baseTask(AiTaskType.DRAMA_TITLE, drama);
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

    private AiTask imageTask(Drama drama, String prompt) {
        AiTask task = baseTask(AiTaskType.DRAMA_COVER, drama);
        task.setModel(aiService.imageModel());
        task.setEndpoint("/images/generations");
        task.setPrompt(prompt);
        task.setRequestPayload(mapOf(
                "model", aiService.imageModel(),
                "prompt", prompt,
                "n", 1,
                "size", aiService.imageSize(),
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

    private Drama saveCoverResult(Drama drama, String imageBase64) {
        String outputFormat = aiService.imageOutputFormat();
        drama.setAiCoverUrl(coverStorage.store(imageBase64, outputFormat));
        drama.setAiCoverGenerating(false);
        return repository.save(drama);
    }

    private Drama get(String id) {
        return repository.findById(id)
                .orElseThrow(() -> new BusinessException("DRAMA_NOT_FOUND", "短剧不存在", HttpStatus.NOT_FOUND));
    }

    private String dramaContext(Drama drama) {
        return """
                原始剧名：%s
                简介：%s
                原始封面：%s
                """.formatted(
                blankToNone(drama.getTitle()),
                blankToNone(drama.getSummary()),
                blankToNone(drama.getCoverUrl())
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

    private String blankToNone(String value) {
        return value == null || value.isBlank() ? "无" : value;
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
