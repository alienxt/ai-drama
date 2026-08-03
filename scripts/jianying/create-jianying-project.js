#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const os = require('os');
const crypto = require('crypto');
const { execFileSync, spawn } = require('child_process');

const DEFAULTS = {
  bgmVolume: 0.35,
  captionScale: 0.18,
  captionTextSize: 8,
  captureDelay: 2,
  clipCount: 24,
  editorDelay: 8,
  homepageDelay: 5,
  homeNavClickXRatio: 0.05,
  homeNavClickYRatio: 0.31,
  draftCardClickXRatio: 0.16,
  draftCardClickYRatio: 0.34,
};

const AUDIO_DISPLAY_STEMS = [
  '回忆_轻快_叙事',
  '节拍_甜美_欢喜',
  '反转_黄昏_心动',
  '悬念_低频_氛围',
  '温柔_留白_铺底',
  '推进_鼓点_情绪',
];

const VIDEO_TRACK_NAMES = [
  'V1 正片画面',
  'V2 补画面/转场层',
];

const SUBTITLE_TRACK_NAMES = [
  'ST1 中文对白字幕',
];

const DIALOGUE_AUDIO_TRACK_NAME = 'A1 原声对白';

const BGM_AUDIO_TRACK_NAMES = [
  'A2 背景音乐',
  'A3 环境氛围',
  'A4 转场音效',
];

const HELP = `
Create a Jianying/CapCut desktop draft from local video, SRT and BGM files.

Usage:
  node scripts/jianying/create-jianying-project.js \\
    --video /path/episode.mp4 \\
    --srt /path/subtitles.srt \\
    --bgm /path/music.mp3 \\
    --template /path/to/template-draft \\
    --name "剧名_第99集_剪辑工程" \\
    --overwrite

Common options:
  --video <file>          Required source video.
  --srt <file>            Optional SRT captions. If omitted, no text track is created.
  --bgm <file>            Optional BGM. Can be repeated.
  --audio <file>          Alias of --bgm for backward compatibility.
  --template <dir>        Template draft dir. If omitted, uses the newest usable local draft.
  --draft-root <dir>      Jianying draft root. Defaults to the local OS path.
  --name <name>           Draft name. Defaults to "<video-name>_剪辑工程".
  --clip-count <n>        Physical video clips on the timeline. Default: 24.
  --output-dir <dir>      Where result JSON and optional screenshot are written.
  --overwrite             Replace an existing draft with the same name.

Proof/screenshot options:
  --open                  Launch Jianying after creating the draft.
  --open-draft            Best-effort UI automation: open the newest draft card.
  --capture               Save a desktop screenshot after the optional open/open-draft step.
  --screenshot <file>     Screenshot path. Implies --capture.
  --capture-delay <sec>   Extra wait before screenshot. Default: 2.
  --full-screen-capture   Capture the whole screen instead of the Jianying/CapCut window.
  --close-existing        Close existing Jianying process before opening.
  --jianying-app <path>   App path override. Useful on Windows installs.
  --ffmpeg <path>         FFmpeg command/path.
  --ffprobe <path>        FFprobe command/path. Defaults to sibling of --ffmpeg.

Environment overrides:
  JIANYING_DRAFT_ROOT, JIANYING_APP
`;

function fail(message) {
  throw new Error(message);
}

function normalizeKey(key) {
  return key.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
}

function parseArgs(argv) {
  const args = {
    ...DEFAULTS,
    bgm: [],
    capture: false,
    closeExisting: false,
    fullScreenCapture: false,
    open: false,
    openDraft: false,
    overwrite: false,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--help' || arg === '-h') {
      args.help = true;
      continue;
    }
    if (!arg.startsWith('--')) fail(`Unexpected argument: ${arg}`);
    const key = normalizeKey(arg.slice(2));
    if (['capture', 'closeExisting', 'fullScreenCapture', 'open', 'openDraft', 'overwrite'].includes(key)) {
      args[key] = true;
      continue;
    }
    const value = argv[i + 1];
    if (!value || value.startsWith('--')) fail(`Missing value for ${arg}`);
    if (key === 'bgm' || key === 'audio') {
      args.bgm.push(value);
    } else {
      args[key] = value;
    }
    i += 1;
  }
  if (args.screenshot) args.capture = true;
  return args;
}

function uuid() {
  return crypto.randomUUID().toUpperCase();
}

function localId() {
  return crypto.randomUUID().toLowerCase();
}

function nowUs() {
  return Date.now() * 1000;
}

function toUs(seconds) {
  return Math.round(seconds * 1000000);
}

function fromUs(us) {
  return us / 1000000;
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function createRng(seedText) {
  const digest = crypto.createHash('sha256').update(String(seedText)).digest();
  let state = digest.readUInt32BE(0) || 1;
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 0x100000000;
  };
}

function randomBetween(rng, min, max) {
  return min + (max - min) * rng();
}

function randomInt(rng, min, max) {
  return Math.floor(randomBetween(rng, min, max + 1));
}

function pick(rng, values) {
  return values[Math.min(values.length - 1, Math.floor(rng() * values.length))];
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

function writeJson(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`);
}

function existsDir(dir) {
  try {
    return fs.statSync(dir).isDirectory();
  } catch {
    return false;
  }
}

function resolveExistingFile(file, label) {
  const resolved = path.resolve(file);
  if (!fs.existsSync(resolved)) fail(`${label} not found: ${resolved}`);
  return resolved;
}

function sanitizeName(name) {
  return String(name)
    .replace(/[<>:"/\\|?*\u0000-\u001F]/g, '_')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 120);
}

function candidateDraftRoots() {
  if (process.env.JIANYING_DRAFT_ROOT) return [process.env.JIANYING_DRAFT_ROOT];
  const home = os.homedir();
  if (process.platform === 'win32') {
    const local = process.env.LOCALAPPDATA || path.join(home, 'AppData', 'Local');
    return [
      path.join(local, 'JianyingPro', 'User Data', 'Projects', 'com.lveditor.draft'),
      path.join(local, 'CapCut', 'User Data', 'Projects', 'com.lveditor.draft'),
    ];
  }
  if (process.platform === 'darwin') {
    return [
      path.join(home, 'Movies', 'JianyingPro', 'User Data', 'Projects', 'com.lveditor.draft'),
      path.join(home, 'Library', 'Containers', 'com.lemon.lvpro', 'Data', 'Movies', 'JianyingPro', 'User Data', 'Projects', 'com.lveditor.draft'),
    ];
  }
  return [
    path.join(home, 'JianyingPro', 'User Data', 'Projects', 'com.lveditor.draft'),
  ];
}

function defaultDraftRoot() {
  const candidates = candidateDraftRoots();
  return candidates.find(existsDir) || candidates[0];
}

function ffprobePathForFfmpeg(ffmpegBin) {
  const value = String(ffmpegBin || 'ffmpeg').trim();
  const parsed = path.parse(value);
  const lower = parsed.base.toLowerCase();
  if (lower === 'ffmpeg.exe') return parsed.dir ? path.join(parsed.dir, 'ffprobe.exe') : 'ffprobe.exe';
  if (lower === 'ffmpeg') return parsed.dir ? path.join(parsed.dir, 'ffprobe') : 'ffprobe';
  if (lower.startsWith('ffmpeg')) {
    return path.join(parsed.dir, parsed.base.replace(/^ffmpeg/i, 'ffprobe'));
  }
  return 'ffprobe';
}

function ensureInside(parent, child) {
  const parentReal = fs.realpathSync(parent);
  const childPath = path.resolve(child);
  if (childPath !== parentReal && !childPath.startsWith(`${parentReal}${path.sep}`)) {
    fail(`Refusing to write outside draft root: ${childPath}`);
  }
}

function emptyDirInside(parent, child) {
  ensureInside(parent, child);
  fs.rmSync(child, { recursive: true, force: true });
  fs.mkdirSync(child, { recursive: true });
}

function ffprobe(file, ffprobeBin) {
  const raw = execFileSync(ffprobeBin, [
    '-v', 'error',
    '-show_streams',
    '-show_format',
    '-of', 'json',
    file,
  ], { encoding: 'utf8' });
  return JSON.parse(raw);
}

function mediaInfo(file, ffprobeBin) {
  const info = ffprobe(file, ffprobeBin);
  const video = info.streams.find((stream) => stream.codec_type === 'video');
  const audio = info.streams.find((stream) => stream.codec_type === 'audio');
  const duration = Number(info.format.duration || video?.duration || audio?.duration || 0);
  return {
    durationUs: toUs(duration),
    durationSeconds: duration,
    hasAudio: Boolean(audio),
    height: video ? Number(video.height) : 0,
    width: video ? Number(video.width) : 0,
  };
}

function parseTimestamp(value) {
  const match = String(value).trim().match(/^(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})$/);
  if (!match) fail(`Invalid SRT timestamp: ${value}`);
  const [, hh, mm, ss, ms] = match;
  return toUs(Number(hh) * 3600 + Number(mm) * 60 + Number(ss) + Number(ms.padEnd(3, '0')) / 1000);
}

function parseSrt(file, timelineDurationUs) {
  if (!file) return [];
  const text = fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, '');
  const blocks = text.split(/\r?\n\s*\r?\n/);
  const captions = [];
  for (const block of blocks) {
    const lines = block.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    if (lines.length < 2) continue;
    if (/^\d+$/.test(lines[0])) lines.shift();
    const timeLine = lines.shift();
    const match = timeLine.match(/(.+?)\s+-->\s+(.+?)(?:\s+.*)?$/);
    if (!match) continue;
    const start = Math.max(0, parseTimestamp(match[1]));
    const end = Math.min(timelineDurationUs, parseTimestamp(match[2]));
    const captionText = lines
      .join(' ')
      .replace(/<[^>]+>/g, '')
      .replace(/\s+/g, ' ')
      .trim();
    if (captionText && end > start) {
      captions.push({ start, duration: end - start, text: captionText });
    }
  }
  return captions;
}

function splitRanges(totalUs, count, rng = Math.random) {
  const totalSeconds = fromUs(totalUs);
  const durationBasedLimit = Math.max(1, Math.floor(totalSeconds / 1.25));
  const safeCount = Math.max(1, Math.min(Number(count), durationBasedLimit));
  const baseDuration = totalUs / safeCount;
  const minDuration = Math.max(600000, Math.min(1800000, baseDuration * 0.42));
  const weights = Array.from({ length: safeCount }, (_, index) => {
    const pulse = index % 5 === 0 ? 1.45 : index % 3 === 0 ? 0.72 : 1.0;
    return randomBetween(rng, 0.58, 1.75) * pulse;
  });
  let durations = weights.map((weight) => Math.round((totalUs * weight) / weights.reduce((sum, item) => sum + item, 0)));
  durations = durations.map((duration) => Math.max(minDuration, duration));
  let drift = durations.reduce((sum, duration) => sum + duration, 0) - totalUs;
  while (drift > 0) {
    const adjustableIndexes = durations
      .map((duration, index) => ({ duration, index }))
      .filter((item) => item.duration > minDuration + 10000)
      .sort((left, right) => right.duration - left.duration);
    if (!adjustableIndexes.length) break;
    for (const item of adjustableIndexes) {
      if (drift <= 0) break;
      const delta = Math.min(drift, item.duration - minDuration);
      durations[item.index] -= delta;
      drift -= delta;
    }
  }
  if (drift < 0) durations[durations.length - 1] += -drift;
  const ranges = [];
  let start = 0;
  for (let i = 0; i < durations.length; i += 1) {
    const duration = i === durations.length - 1 ? totalUs - start : durations[i];
    ranges.push({ start, duration });
    start += duration;
  }
  return ranges;
}

function speedForClip(index, rng) {
  const rhythm = index % 7;
  if (rhythm === 2) return 0.9;
  if (rhythm === 4) return 1.1;
  if (rhythm === 6) return 1.2;
  return rng() > 0.84 ? pick(rng, [0.9, 1.1, 1.2]) : 1.0;
}

function splitVideo({ source, outputDir, ranges, ffmpegBin }) {
  const ext = path.extname(source) || '.mp4';
  const baseName = sanitizeName(path.basename(source, ext));
  return ranges.map((range, index) => {
    const fileName = `${baseName}-part${String(index + 1).padStart(2, '0')}${ext}`;
    const output = path.join(outputDir, fileName);
    execFileSync(ffmpegBin, [
      '-y',
      '-ss', String(fromUs(range.start)),
      '-i', source,
      '-t', String(fromUs(range.duration)),
      '-c', 'copy',
      '-avoid_negative_ts', 'make_zero',
      output,
    ], { stdio: 'ignore' });
    return { ...range, fileName, output };
  });
}

function extractDialogueAudio({ source, outputDir, ffmpegBin }) {
  const baseName = sanitizeName(path.basename(source, path.extname(source)));
  const fileName = `${baseName}-原声对白.wav`;
  const output = path.join(outputDir, fileName);
  execFileSync(ffmpegBin, [
    '-y',
    '-i', source,
    '-vn',
    '-ac', '2',
    '-ar', '48000',
    '-c:a', 'pcm_s16le',
    output,
  ], { stdio: 'ignore' });
  return { fileName, output };
}

function defaultClip(scale = 1.0, x = 0.0, y = 0.0) {
  return {
    alpha: 1.0,
    flip: { horizontal: false, vertical: false },
    rotation: 0.0,
    scale: { x: scale, y: scale },
    transform: { x, y },
  };
}

function makeTrack(type, segments, name = '') {
  return {
    attribute: 0,
    flag: 0,
    id: uuid(),
    is_default_name: !name,
    name,
    segments,
    type,
  };
}

function makeVideoSegment(baseSegment, materialId, targetRange, index, extraRefs, speed = 1.0, options = {}) {
  const segment = clone(baseSegment);
  segment.id = uuid();
  segment.material_id = materialId;
  segment.source_timerange = { start: options.sourceStart || 0, duration: targetRange.duration };
  segment.target_timerange = targetRange;
  delete segment.render_timerange;
  segment.render_index = index;
  segment.track_render_index = 0;
  segment.extra_material_refs = extraRefs;
  segment.keyframe_refs = [];
  segment.common_keyframes = [];
  segment.clip = options.clip || defaultClip();
  segment.speed = speed;
  segment.uniform_scale = { on: true, value: 1.0 };
  segment.visible = true;
  return segment;
}

function makeAudioMaterial({ id, localMaterialId, fileName, durationUs, filePath }) {
  return {
    category_id: '',
    category_name: 'local',
    check_flag: 1,
    duration: durationUs,
    effect_id: '',
    formula_id: '',
    id,
    local_material_id: localMaterialId,
    material_id: '',
    name: fileName,
    path: filePath,
    request_id: '',
    resource_id: '',
    source_platform: 0,
    team_id: '',
    text_id: '',
    tone_category_id: '',
    tone_category_name: '',
    type: 'extract_music',
    video_id: '',
    wave_points: [],
  };
}

function makeAudioSegment(materialId, sourceStartUs, startUs, durationUs, extraRefs, volume) {
  return {
    cartoon: false,
    clip: null,
    common_keyframes: [],
    extra_material_refs: extraRefs,
    group_id: '',
    id: uuid(),
    intensifies_audio: false,
    is_placeholder: false,
    is_tone_modify: false,
    keyframe_refs: [],
    last_nonzero_volume: volume,
    material_id: materialId,
    render_index: 0,
    reverse: false,
    source_timerange: { start: sourceStartUs, duration: durationUs },
    speed: 1.0,
    target_timerange: { start: startUs, duration: durationUs },
    template_id: '',
    track_render_index: 0,
    visible: true,
    volume,
  };
}

function escapeText(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function makeTextMaterial({ id, text, textSize, color = '#FFFFFF', alpha = 1.0 }) {
  return {
    add_type: 0,
    alignment: 1,
    background_alpha: 0.0,
    background_color: '',
    bold_width: 0.0,
    border_alpha: 1.0,
    border_color: '#000000',
    border_width: 0.025,
    check_flag: 7,
    content: `<font id="" path="">${escapeText(text)}</font>`,
    font_category: '',
    font_id: '',
    font_name: '',
    font_path: '',
    font_resource_id: '',
    font_size: textSize,
    global_alpha: alpha,
    id,
    initial_scale: 1.0,
    italic_degree: 0,
    ktv_color: '',
    language: '',
    layer_weight: 1,
    letter_spacing: 0.0,
    line_spacing: 0.0,
    preset_category: '',
    preset_category_id: '',
    preset_has_set_alignment: false,
    preset_id: '',
    preset_index: 0,
    preset_name: '',
    recognize_type: 0,
    shadow_alpha: 0.75,
    shadow_angle: -45.0,
    shadow_color: '#000000',
    shadow_distance: 4.0,
    shadow_point: { x: 1.0, y: -1.0 },
    shadow_smoothing: 0.4,
    shape_clip_x: false,
    shape_clip_y: false,
    style_name: '',
    sub_type: 0,
    text_alpha: alpha,
    text_color: color,
    text_size: textSize,
    type: 'text',
    underline: false,
    vertical: false,
  };
}

function makeTextSegment(materialId, caption, index, scale, y = -0.78) {
  return {
    clip: {
      ...defaultClip(scale, 0.0, y),
    },
    common_keyframes: [],
    extra_material_refs: [],
    group_id: '',
    id: uuid(),
    is_placeholder: false,
    keyframe_refs: [],
    material_id: materialId,
    render_index: index,
    source_timerange: null,
    target_timerange: { start: caption.start, duration: caption.duration },
    template_id: '',
    track_render_index: 0,
    visible: true,
  };
}

function distributeSegmentsAcrossTracks(segments, trackCount) {
  const count = Math.max(1, Math.min(trackCount, segments.length || 1));
  const tracks = Array.from({ length: count }, () => []);
  segments.forEach((segment, index) => {
    tracks[index % count].push(segment);
  });
  return tracks.filter((track) => track.length);
}

function assignTrackRenderIndex(segments, trackIndex) {
  segments.forEach((segment, index) => {
    segment.render_index = index;
    segment.track_render_index = trackIndex;
  });
  return segments;
}

function namedSegmentTracks({ segments, names, count }) {
  return distributeSegmentsAcrossTracks(segments, count).map((trackSegments, index) => ({
    name: names[index] || `${names[0] || '轨道'} ${index + 1}`,
    segments: trackSegments,
  }));
}

function makeOverlayVideoSegments({
  baseSegment,
  baseExtras,
  draftMaterials,
  rng,
  sourceSegments,
  totalUs,
}) {
  if (sourceSegments.length < 8 || totalUs < 12000000) return [];
  const desiredCount = Math.min(randomInt(rng, 4, 7), Math.max(1, Math.floor(sourceSegments.length / 4)));
  const candidateIndexes = [];
  for (let index = 2; index < sourceSegments.length - 1; index += 1) {
    if (index % 3 === 0 || index % 5 === 0) candidateIndexes.push(index);
  }
  const segments = [];
  while (segments.length < desiredCount && candidateIndexes.length) {
    const pickedOffset = randomInt(rng, 0, candidateIndexes.length - 1);
    const [sourceIndex] = candidateIndexes.splice(pickedOffset, 1);
    const source = sourceSegments[sourceIndex];
    const maxDuration = Math.min(source.target_timerange.duration, Math.round(randomBetween(rng, 900000, 1800000)));
    if (maxDuration <= 500000) continue;
    const offsetMax = Math.max(0, source.target_timerange.duration - maxDuration);
    const sourceOffset = Math.round(randomBetween(rng, 0, offsetMax));
    const extraRefs = makeExtraRefs(draftMaterials, baseExtras, [
      'speeds',
      'canvases',
    ], (key, material) => {
      if (key === 'speeds') {
        material.speed = 1.0;
        material.mode = 0;
        material.curve_speed = null;
      }
    });
    const clip = defaultClip(
      randomBetween(rng, 1.03, 1.08),
      randomBetween(rng, -0.018, 0.018),
      randomBetween(rng, -0.018, 0.018),
    );
    segments.push(makeVideoSegment(
      baseSegment,
      source.material_id,
      {
        start: source.target_timerange.start + sourceOffset,
        duration: maxDuration,
      },
      segments.length,
      extraRefs,
      1.0,
      {
        clip,
        sourceStart: sourceOffset,
      },
    ));
  }
  return segments.sort((left, right) => left.target_timerange.start - right.target_timerange.start);
}

function makeTimelineCaption(text, start, duration) {
  return { text, start, duration };
}

function makeAuxiliaryTextTrack({
  labels,
  totalUs,
  rng,
  textMaterials,
  scale = 0.12,
  y = -1.18,
  color = '#D8B4FE',
  textSize = 8,
}) {
  const segments = [];
  const safeTotal = Math.max(totalUs, 1);
  labels.forEach((label, index) => {
    const duration = Math.min(
      Math.round(randomBetween(rng, 1800000, 5200000)),
      Math.max(600000, safeTotal - 100000),
    );
    const startMax = Math.max(0, safeTotal - duration);
    const start = Math.round(randomBetween(rng, 0, startMax));
    const material = makeTextMaterial({
      id: uuid(),
      text: label,
      textSize,
      color,
      alpha: 0.0,
    });
    textMaterials.push(material);
    segments.push(makeTextSegment(material.id, makeTimelineCaption(label, start, duration), index, scale, y));
  });
  return segments.sort((left, right) => left.target_timerange.start - right.target_timerange.start);
}

function makeAudioPlan({ bgmFiles, audioInfos, totalUs, rng }) {
  if (!bgmFiles.length) return [[], [], []];
  const plans = [[], [], []];
  const makePlan = ({ audioIndex, start, duration }) => {
    const audioDuration = audioInfos[audioIndex].durationUs;
    const safeDuration = Math.min(audioDuration, duration, totalUs - start);
    if (safeDuration <= 500000) return null;
    const sourceStartMax = Math.max(0, audioDuration - safeDuration);
    return {
      audioIndex,
      duration: safeDuration,
      sourceStart: Math.round(randomBetween(rng, 0, sourceStartMax)),
      start,
    };
  };

  const bedAudioIndex = randomInt(rng, 0, bgmFiles.length - 1);
  const bedDuration = Math.min(
    audioInfos[bedAudioIndex].durationUs,
    Math.round(totalUs * randomBetween(rng, 0.55, 0.82)),
    totalUs,
  );
  const bedStartMax = Math.max(0, Math.min(2200000, totalUs - bedDuration));
  const bedPlan = makePlan({
    audioIndex: bedAudioIndex,
    start: Math.round(randomBetween(rng, 0, bedStartMax)),
    duration: bedDuration,
  });
  if (bedPlan) plans[0].push(bedPlan);

  const ambienceCount = totalUs >= 20000000 ? randomInt(rng, 2, 3) : 1;
  const ambienceSlot = totalUs / Math.max(1, ambienceCount + 1);
  for (let index = 0; index < ambienceCount; index += 1) {
    const audioIndex = randomInt(rng, 0, bgmFiles.length - 1);
    const audioDuration = audioInfos[audioIndex].durationUs;
    const desired = Math.min(audioDuration, Math.round(randomBetween(rng, 5800000, 14000000)));
    const slotStart = Math.round(ambienceSlot * index + randomBetween(rng, 1800000, 4500000));
    const startMax = Math.max(0, totalUs - desired);
    const plan = makePlan({
      audioIndex,
      start: Math.min(slotStart, startMax),
      duration: desired,
    });
    if (plan) plans[1].push(plan);
  }

  const effectCount = totalUs >= 20000000 ? randomInt(rng, 3, 5) : randomInt(rng, 1, 2);
  const effectSlot = totalUs / Math.max(1, effectCount + 1);
  for (let index = 0; index < effectCount; index += 1) {
    const audioIndex = randomInt(rng, 0, bgmFiles.length - 1);
    const desired = Math.round(randomBetween(rng, 900000, 2600000));
    const centered = Math.round(effectSlot * (index + 1));
    const start = Math.max(0, Math.min(totalUs - desired, centered + Math.round(randomBetween(rng, -1300000, 1300000))));
    const plan = makePlan({ audioIndex, start, duration: desired });
    if (plan) plans[2].push(plan);
  }
  return plans.map((track) => track.sort((left, right) => left.start - right.start));
}

function makeAudioDisplayName(file, index) {
  const ext = path.extname(file) || '.mp3';
  const stem = AUDIO_DISPLAY_STEMS[index % AUDIO_DISPLAY_STEMS.length];
  return `${String(index + 1).padStart(2, '0')}-${stem}${ext}`;
}

function resetMaterialBuckets(materials, keys) {
  for (const key of keys) materials[key] = [];
}

function makeExtraRefs(materials, templates, keys, configure = null) {
  const refs = [];
  for (const key of keys) {
    const template = templates[key];
    if (!template) continue;
    const material = clone(template);
    material.id = uuid();
    if (configure) configure(key, material);
    materials[key].push(material);
    refs.push(material.id);
  }
  return refs;
}

function findTemplateDraft(draftRoot, explicitTemplate) {
  if (explicitTemplate) {
    const template = path.resolve(explicitTemplate);
    if (!existsDir(template)) fail(`Template draft not found: ${template}`);
    return template;
  }
  const rootFile = path.join(draftRoot, 'root_meta_info.json');
  if (!fs.existsSync(rootFile)) {
    fail(`Template is required because root_meta_info.json was not found in: ${draftRoot}`);
  }
  const root = readJson(rootFile);
  const stores = Array.isArray(root.all_draft_store) ? root.all_draft_store : [];
  for (const item of stores) {
    const draftDir = item.draft_fold_path;
    const draftInfoFile = draftDir && path.join(draftDir, 'draft_info.json');
    if (!draftInfoFile || !fs.existsSync(draftInfoFile)) continue;
    try {
      const draft = readJson(draftInfoFile);
      const hasVideoMaterial = Array.isArray(draft.materials?.videos) && draft.materials.videos.length > 0;
      const hasVideoSegment = Array.isArray(draft.tracks)
        && draft.tracks.some((track) => track.type === 'video' && track.segments?.length);
      if (hasVideoMaterial && hasVideoSegment) return draftDir;
    } catch {
      // Keep looking for another usable draft.
    }
  }
  fail(`No usable template draft found under: ${draftRoot}`);
}

function upsertRootEntry(rootFile, entry, overwrite) {
  const root = readJson(rootFile);
  if (!Array.isArray(root.all_draft_store)) {
    fail(`Unexpected root_meta_info.json: ${rootFile}`);
  }
  const existingIndex = root.all_draft_store.findIndex((item) => item.draft_name === entry.draft_name);
  if (existingIndex >= 0) {
    if (!overwrite) fail(`Draft already exists: ${entry.draft_name}; pass --overwrite`);
    root.all_draft_store.splice(existingIndex, 1);
  }
  root.all_draft_store.unshift(entry);
  root.draft_ids = root.all_draft_store.length;
  writeJson(rootFile, root);
}

function updateDraftMeta(draftDir, draftName, draftId, videoMetas, audioMetas, timestampUs) {
  const file = path.join(draftDir, 'draft_meta_info.json');
  const meta = readJson(file);
  const totalVideoSize = videoMetas.reduce((sum, item) => sum + item.size, 0);
  const totalAudioSize = audioMetas.reduce((sum, item) => sum + item.size, 0);
  const maxDuration = videoMetas.reduce((sum, item) => sum + item.durationUs, 0);
  meta.draft_cover = 'draft_cover.jpg';
  meta.draft_fold_path = draftDir;
  meta.draft_id = draftId;
  meta.draft_name = draftName;
  meta.draft_root_path = path.dirname(draftDir);
  meta.tm_draft_create = timestampUs;
  meta.tm_draft_modified = timestampUs;
  meta.tm_duration = maxDuration;
  meta.draft_timeline_materials_size_ = totalVideoSize + totalAudioSize;
  const videoEntries = videoMetas.map((videoMeta) => ({
    create_time: Math.floor(timestampUs / 1000000),
    duration: videoMeta.durationUs,
    extra_info: videoMeta.name,
    file_Path: `./Resources/media/${videoMeta.name}`,
    height: videoMeta.height,
    id: videoMeta.localMaterialId,
    import_time: Math.floor(timestampUs / 1000000),
    import_time_ms: timestampUs,
    item_source: 1,
    md5: '',
    metetype: 'video',
    roughcut_time_range: { duration: videoMeta.durationUs, start: 0 },
    sub_time_range: { duration: -1, start: -1 },
    type: 0,
    width: videoMeta.width,
  }));
  const audioEntries = audioMetas.map((audioMeta) => ({
    create_time: Math.floor(timestampUs / 1000000),
    duration: audioMeta.durationUs,
    extra_info: audioMeta.name,
    file_Path: `./Resources/audio/${audioMeta.name}`,
    height: 0,
    id: audioMeta.localMaterialId,
    import_time: Math.floor(timestampUs / 1000000),
    import_time_ms: timestampUs,
    item_source: 1,
    md5: '',
    metetype: 'audio',
    roughcut_time_range: { duration: audioMeta.durationUs, start: 0 },
    sub_time_range: { duration: -1, start: -1 },
    type: 1,
    width: 0,
  }));
  meta.draft_materials = [
    { type: 0, value: videoEntries },
    { type: 1, value: audioEntries },
    { type: 2, value: [] },
    { type: 3, value: [] },
    { type: 6, value: [] },
    { type: 7, value: [] },
    { type: 8, value: [] },
  ];
  writeJson(file, meta);
}

function updateVirtualStore(draftDir, videoMetas, audioMetas, timestampUs) {
  const file = path.join(draftDir, 'draft_virtual_store.json');
  const store = fs.existsSync(file) ? readJson(file) : { draft_materials: [], draft_virtual_store: [] };
  const materialRows = [
    { creation_time: 0, display_name: '', filter_type: 0, id: '', import_time: 0, import_time_us: 0, sort_sub_type: 0, sort_type: 0 },
    ...videoMetas.map((videoMeta) => ({
      creation_time: Math.floor(timestampUs / 1000000),
      display_name: videoMeta.name,
      filter_type: 0,
      id: videoMeta.localMaterialId,
      import_time: Math.floor(timestampUs / 1000000),
      import_time_us: timestampUs,
      sort_sub_type: 0,
      sort_type: 0,
    })),
    ...audioMetas.map((audioMeta) => ({
      creation_time: Math.floor(timestampUs / 1000000),
      display_name: audioMeta.name,
      filter_type: 0,
      id: audioMeta.localMaterialId,
      import_time: Math.floor(timestampUs / 1000000),
      import_time_us: timestampUs,
      sort_sub_type: 0,
      sort_type: 0,
    })),
  ];
  store.draft_virtual_store = [
    { type: 0, value: materialRows },
    {
      type: 1,
      value: [
        ...videoMetas.map((videoMeta) => ({ parent_id: '', child_id: videoMeta.localMaterialId })),
        ...audioMetas.map((audioMeta) => ({ parent_id: '', child_id: audioMeta.localMaterialId })),
      ],
    },
    { type: 2, value: [] },
  ];
  writeJson(file, store);
}

function collectMaterialIds(materials) {
  const ids = new Set();
  for (const value of Object.values(materials || {})) {
    if (!Array.isArray(value)) continue;
    for (const item of value) {
      if (item && item.id) ids.add(item.id);
    }
  }
  return ids;
}

function validateRefs(draft) {
  const ids = collectMaterialIds(draft.materials);
  const missing = [];
  for (const track of draft.tracks || []) {
    for (const segment of track.segments || []) {
      if (segment.material_id && !ids.has(segment.material_id)) missing.push(segment.material_id);
      for (const ref of segment.extra_material_refs || []) {
        if (!ids.has(ref)) missing.push(ref);
      }
    }
  }
  return [...new Set(missing)];
}

function candidateApps() {
  if (process.env.JIANYING_APP) return [process.env.JIANYING_APP];
  if (process.platform === 'darwin') {
    return [
      '/Applications/VideoFusion-macOS.app',
      '/Applications/剪映专业版.app',
      '/Applications/JianyingPro.app',
      '/Applications/CapCut.app',
    ];
  }
  if (process.platform === 'win32') {
    const local = process.env.LOCALAPPDATA || '';
    const pf = process.env.ProgramFiles || '';
    const pf86 = process.env['ProgramFiles(x86)'] || '';
    return [
      path.join(local, 'JianyingPro', 'JianyingPro.exe'),
      path.join(local, 'JianyingPro', 'Apps', 'JianyingPro.exe'),
      path.join(local, 'Programs', 'JianyingPro', 'JianyingPro.exe'),
      path.join(pf, 'JianyingPro', 'JianyingPro.exe'),
      path.join(pf86, 'JianyingPro', 'JianyingPro.exe'),
      path.join(local, 'CapCut', 'CapCut.exe'),
      path.join(local, 'CapCut', 'Apps', 'CapCut.exe'),
      path.join(pf, 'CapCut', 'CapCut.exe'),
    ];
  }
  return [];
}

function findJianyingApp(explicitApp) {
  if (explicitApp) return path.resolve(explicitApp);
  return candidateApps().find((candidate) => candidate && fs.existsSync(candidate)) || null;
}

function unique(values) {
  return [...new Set(values.filter(Boolean))];
}

function macBundleId(appPath) {
  if (!appPath || !existsDir(appPath)) return null;
  const infoPlist = path.join(appPath, 'Contents', 'Info.plist');
  if (!fs.existsSync(infoPlist)) return null;
  try {
    return execFileSync('/usr/libexec/PlistBuddy', [
      '-c',
      'Print CFBundleIdentifier',
      infoPlist,
    ], { encoding: 'utf8' }).trim();
  } catch {
    return null;
  }
}

function appleScriptString(value) {
  return `"${String(value).replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`;
}

function macJianyingProcessNames(appPath) {
  const appName = appPath ? path.basename(appPath, '.app') : null;
  return unique([
    appName,
    'VideoFusion-macOS',
    'JianyingPro',
    'Jianying',
    '剪映专业版',
    '剪映',
    'CapCut',
  ]);
}

function macFrontProcessName() {
  try {
    return osascript('tell application "System Events" to return name of first application process whose frontmost is true');
  } catch {
    return null;
  }
}

function macBringJianyingToFront(appPath) {
  for (const processName of macJianyingProcessNames(appPath)) {
    try {
      osascript(`tell application "System Events" to tell process ${appleScriptString(processName)} to set frontmost to true`);
      sleep(0.4);
      if (macFrontProcessName() === processName) return processName;
    } catch {
      // Try the next known process name.
    }
  }
  return null;
}

function macVisibleTopLeftBounds() {
  const swift = `
import AppKit
let screen = NSScreen.main!
let frame = screen.frame
let visible = screen.visibleFrame
let x = Int(visible.origin.x)
let y = Int(frame.height - visible.origin.y - visible.height)
print("\\(x),\\(y),\\(Int(visible.width)),\\(Int(visible.height))")
`;
  try {
    const output = execFileSync('swift', ['-e', swift], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    }).trim();
    const values = output.split(',').map(Number);
    if (values.length === 4 && values.every(Number.isFinite) && values[2] > 0 && values[3] > 0) {
      return values;
    }
  } catch {
    // Use a conservative large-window fallback below.
  }
  return [0, 38, 1280, 800];
}

function macJianyingWindowCaptureTarget(appPath = null) {
  const processNames = macJianyingProcessNames(appPath);
  const processList = JSON.stringify(processNames);
  const swift = `
import CoreGraphics
import Foundation

let processNames = Set(${processList})
let options: CGWindowListOption = [.optionOnScreenOnly, .excludeDesktopElements]
guard let windows = CGWindowListCopyWindowInfo(options, kCGNullWindowID) as? [[String: Any]] else {
    exit(2)
}

func matchesOwner(_ owner: String) -> Bool {
    let lowerOwner = owner.lowercased()
    for name in processNames {
        let lowerName = name.lowercased()
        if owner == name || lowerOwner.contains(lowerName) || lowerName.contains(lowerOwner) {
            return true
        }
    }
    return false
}

for window in windows {
    guard
        let owner = window[kCGWindowOwnerName as String] as? String,
        matchesOwner(owner),
        let layer = window[kCGWindowLayer as String] as? Int,
        layer == 0,
        let windowId = window[kCGWindowNumber as String] as? Int,
        let bounds = window[kCGWindowBounds as String] as? [String: Any],
        let x = bounds["X"] as? Double,
        let y = bounds["Y"] as? Double,
        let width = bounds["Width"] as? Double,
        let height = bounds["Height"] as? Double,
        width >= 480,
        height >= 320
    else {
        continue
    }
    print("\\(windowId),\\(Int(x)),\\(Int(y)),\\(Int(width)),\\(Int(height))")
    exit(0)
}

exit(3)
`;
  try {
    const output = execFileSync('swift', ['-e', swift], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    }).trim();
    const values = output.split(',').map(Number);
    if (values.length === 5 && values.every(Number.isFinite) && values[3] > 0 && values[4] > 0) {
      return {
        windowId: Math.round(values[0]),
        bounds: values.slice(1),
      };
    }
  } catch {
    // Fall back to Accessibility-based window bounds below.
  }
  return null;
}

function macWindowBoundsViaCoreGraphics(appPath = null) {
  return macJianyingWindowCaptureTarget(appPath)?.bounds || null;
}

function macNormalizeJianyingWindow(appPath) {
  const processName = macBringJianyingToFront(appPath);
  if (!processName) return false;
  const [x, y, w, h] = macVisibleTopLeftBounds();
  const minW = Math.min(1100, Math.max(640, Math.round(w * 0.8)));
  const minH = Math.min(700, Math.max(480, Math.round(h * 0.75)));
  const windowLooksLargeEnough = () => {
    const bounds = macWindowBoundsViaCoreGraphics(appPath);
    return Boolean(bounds && bounds[2] >= minW && bounds[3] >= minH);
  };
  const windowLooksUsable = () => {
    const names = macWindowUiNames(appPath);
    return macUiLooksLikeHome(names) || macUiLooksLikeEditor(names);
  };
  const setWindowToVisibleFrame = () => osascript(`
tell application "System Events"
  tell process ${appleScriptString(processName)}
    set position of window 1 to {${Math.round(x)}, ${Math.round(y)}}
    set size of window 1 to {${Math.round(w)}, ${Math.round(h)}}
  end tell
end tell
`);
  const clickZoomButton = () => osascript(`
tell application "System Events"
  tell process ${appleScriptString(processName)}
    if not (exists window 1) then error "window missing"
    set zoomButtons to every button of window 1 whose subrole is "AXZoomButton"
    if (count of zoomButtons) is 0 then error "zoom button missing"
    click item 1 of zoomButtons
  end tell
end tell
`);
  try {
    setWindowToVisibleFrame();
    sleep(0.5);
    if (windowLooksLargeEnough() || windowLooksUsable()) return true;
    clickZoomButton();
    sleep(0.8);
    setWindowToVisibleFrame();
    sleep(0.5);
    return windowLooksLargeEnough() || windowLooksUsable();
  } catch {
    return windowLooksUsable();
  }
}

function macClickStaticText(appPath, text) {
  const processName = macBringJianyingToFront(appPath);
  if (!processName) return false;
  try {
    osascript(`
tell application "System Events"
  tell process ${appleScriptString(processName)}
    click static text ${appleScriptString(text)} of window 1
  end tell
end tell
`);
    return true;
  } catch {
    return false;
  }
}

function macWindowUiNames(appPath) {
  for (const processName of macJianyingProcessNames(appPath)) {
    try {
      return osascript(`
tell application "System Events"
  tell process ${appleScriptString(processName)}
    if not (exists window 1) then error "window missing"
    set uiNames to name of every UI element of window 1
  end tell
end tell
return uiNames as text
`);
    } catch {
      // Try the next known process name.
    }
  }
  return '';
}

function macUiLooksLikeHome(names) {
  const text = String(names || '');
  return text.includes('HomePageDraftTitle:')
    || text.includes('HomePageStart')
    || text.includes('开始创作')
    || text.includes('最近删除');
}

function macUiLooksLikeEditor(names) {
  const text = String(names || '');
  if (!text || macUiLooksLikeHome(text)) return false;
  const hasEditorTimeline = text.includes('VETreeMainCellItem:')
    || text.includes('VETreeSubCellItem:')
    || text.includes('VECollectTitleView:')
    || text.includes('currentProgress')
    || text.includes('totalProgress')
    || text.includes('MTLSText:');
  if (hasEditorTimeline) return true;
  const hasEditorChrome = text.includes('播放器')
    || text.includes('草稿参数')
    || text.includes('导出');
  const hasToolTabs = text.includes('媒体')
    || text.includes('音频')
    || text.includes('文本')
    || text.includes('字幕');
  return hasEditorChrome && hasToolTabs;
}

function macWaitForEditor(appPath, timeoutSeconds = 14) {
  const deadline = Date.now() + Math.max(1, timeoutSeconds) * 1000;
  let lastNames = '';
  while (Date.now() < deadline) {
    lastNames = macWindowUiNames(appPath) || lastNames;
    if (macUiLooksLikeEditor(lastNames)) return true;
    sleep(0.8);
  }
  return false;
}

function macDismissJianyingStartupDialogs(appPath, timeoutSeconds = 8) {
  if (process.platform !== 'darwin') return true;
  const deadline = Date.now() + Math.max(1, timeoutSeconds) * 1000;
  while (Date.now() < deadline) {
    let sawProcess = false;
    let closedDialog = false;
    for (const processName of macJianyingProcessNames(appPath)) {
      try {
        const result = osascript(`
tell application "System Events"
  tell process ${appleScriptString(processName)}
    if not (exists window 1) then return "WAIT"
    set didClose to false
    repeat with currentWindow in windows
      set windowName to ""
      try
        set windowName to name of currentWindow as text
      end try
      if windowName contains "版本更新" or windowName contains "Update" then
        try
          click button 1 of currentWindow
          set didClose to true
        end try
      end if
    end repeat
    if didClose then return "CLOSED"
    return "READY"
  end tell
end tell
`);
        sawProcess = true;
        if (result === 'CLOSED') {
          closedDialog = true;
          break;
        }
        if (result === 'READY') return true;
      } catch {
        // Try the next known process name.
      }
    }
    sleep(closedDialog || !sawProcess ? 0.8 : 0.4);
  }
  return false;
}

function macClickDraftTitle(appPath, draftName) {
  if (!draftName) return false;
  const targetName = `HomePageDraftTitle:${draftName}`;
  for (const processName of macJianyingProcessNames(appPath)) {
    try {
      const boundsText = osascript(`
set targetName to ${appleScriptString(targetName)}
set fallbackName to ${appleScriptString(draftName)}
tell application "System Events"
  tell process ${appleScriptString(processName)}
    if not (exists window 1) then error "window missing"
    set matches to every UI element of window 1 whose name is targetName
    if (count of matches) is 0 then set matches to every UI element of window 1 whose name contains fallbackName
    if (count of matches) is 0 then error "draft card not found"
    set e to item 1 of matches
    set p to position of e
    set s to size of e
    return (item 1 of p as text) & "," & (item 2 of p as text) & "," & (item 1 of s as text) & "," & (item 2 of s as text)
  end tell
end tell
`);
      const [titleX, titleY, titleW, titleH] = boundsText.split(',').map(Number);
      if ([titleX, titleY, titleW, titleH].some((value) => !Number.isFinite(value))) {
        throw new Error(`invalid draft title bounds: ${boundsText}`);
      }
      const titleCenterX = Math.round(titleX + titleW / 2);
      const titleCenterY = Math.round(titleY + titleH / 2);
      const cardClickPoints = [
        [titleCenterX, Math.max(0, Math.round(titleY - 65))],
        [titleCenterX, Math.max(0, Math.round(titleY - 85))],
        [titleCenterX, titleCenterY],
      ];
      for (const [clickX, clickY] of cardClickPoints) {
        macMouseClick(clickX, clickY, 2);
        sleep(1.2);
        if (macWaitForEditor(appPath, 3)) return true;
      }
      return false;
    } catch {
      // Try the next known process name.
    }
  }
  return false;
}

function closeExistingJianying() {
  if (process.platform === 'darwin') {
    for (const name of ['VideoFusion-macOS', 'JianyingPro', 'CapCut']) {
      try { execFileSync('pkill', ['-x', name], { stdio: 'ignore' }); } catch {}
    }
    return;
  }
  if (process.platform === 'win32') {
    const script = 'Get-Process | Where-Object { $_.ProcessName -match "Jianying|CapCut|VideoFusion" } | Stop-Process -Force';
    try { execFileSync('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script], { stdio: 'ignore' }); } catch {}
  }
}

function openJianying(appPath) {
  if (!appPath) return false;
  if (process.platform === 'darwin') {
    execFileSync('open', [appPath], { stdio: 'ignore' });
    activateJianying(appPath);
    macDismissJianyingStartupDialogs(appPath);
    return true;
  }
  if (process.platform === 'win32') {
    const child = spawn(appPath, [], { detached: true, stdio: 'ignore' });
    child.unref();
    return true;
  }
  return false;
}

function sleep(seconds) {
  const millis = Math.max(0, Math.round(seconds * 1000));
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, millis);
}

function osascript(script) {
  return execFileSync('osascript', ['-e', script], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  }).trim();
}

function activateJianying(appPath) {
  if (process.platform === 'darwin') {
    const bundleIds = unique([
      macBundleId(appPath),
      'com.lemon.lvpro',
      'com.lemon.lveditor',
      'com.lemon.capcut',
    ]);
    for (const bundleId of bundleIds) {
      try {
        osascript(`tell application id "${bundleId}" to activate`);
        sleep(0.5);
        const processName = macBringJianyingToFront(appPath);
        if (processName) return true;
      } catch {
        // Try the next known bundle id.
      }
    }
    if (appPath) {
      try {
        execFileSync('open', [appPath], { stdio: 'ignore' });
        sleep(0.5);
        const processName = macBringJianyingToFront(appPath);
        return Boolean(processName);
      } catch {
        return false;
      }
    }
    return false;
  }
  if (process.platform === 'win32') {
    const script = `
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32Focus {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
}
"@
$p = Get-Process | Where-Object { $_.MainWindowHandle -ne 0 -and $_.ProcessName -match "Jianying|CapCut|VideoFusion" } | Select-Object -First 1
if (-not $p) { exit 2 }
[Win32Focus]::SetForegroundWindow($p.MainWindowHandle) | Out-Null
`;
    try {
      execFileSync('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script], { stdio: 'ignore' });
      sleep(0.5);
      return true;
    } catch {
      return false;
    }
  }
  return false;
}

function macFrontWindowBounds(appPath = null) {
  const coreGraphicsBounds = macWindowBoundsViaCoreGraphics(appPath);
  if (coreGraphicsBounds) return coreGraphicsBounds;
  const processName = appPath ? macBringJianyingToFront(appPath) : macFrontProcessName();
  if (!processName) {
    fail(appPath
      ? 'Jianying window was not found; refusing to capture the current desktop.'
      : 'No front window process found');
  }
  let bounds;
  try {
    bounds = osascript(`
tell application "System Events"
  tell process ${appleScriptString(processName)}
    set p to position of window 1
    set s to size of window 1
  end tell
end tell
return (item 1 of p as text) & "," & (item 2 of p as text) & "," & (item 1 of s as text) & "," & (item 2 of s as text)
`);
  } catch (error) {
    fail(`Jianying window bounds unavailable. Tried CoreGraphics first, then macOS Accessibility fallback. Please grant Accessibility permission to the local AI Drama app or osascript/System Events. ${error.message}`);
  }
  return bounds.split(',').map(Number);
}

function macMouseClick(clickX, clickY, clickCount = 1) {
  const count = Math.max(1, Math.round(Number(clickCount) || 1));
  const swift = `
import CoreGraphics
import Foundation

let point = CGPoint(x: ${clickX}, y: ${clickY})
CGWarpMouseCursorPosition(point)
CGAssociateMouseAndMouseCursorPosition(1)

func send(_ type: CGEventType, _ clickState: Int64) {
    if let event = CGEvent(mouseEventSource: nil, mouseType: type, mouseCursorPosition: point, mouseButton: .left) {
        event.setIntegerValueField(.mouseEventClickState, value: clickState)
        event.post(tap: .cghidEventTap)
    }
}

send(.leftMouseDown, 1)
send(.leftMouseUp, 1)
if ${count} > 1 {
    usleep(160000)
    send(.leftMouseDown, 2)
    send(.leftMouseUp, 2)
}
`;
  execFileSync('swift', ['-e', swift], { stdio: 'ignore' });
}

function winOpenDraftByTitle(appPath, draftName) {
  if (!draftName) fail('Draft name is required for Windows draft opening.');
  const script = `
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32DraftOpen {
  [StructLayout(LayoutKind.Sequential)]
  public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
  [DllImport("user32.dll")] public static extern void mouse_event(UInt32 dwFlags, UInt32 dx, UInt32 dy, UInt32 dwData, UIntPtr dwExtraInfo);
}
"@

$draftName = ${psSingle(draftName)}
$appPath = ${psSingle(appPath || '')}

function Get-TargetProcess {
  $baseName = ''
  if ($appPath) {
    try { $baseName = [System.IO.Path]::GetFileNameWithoutExtension($appPath) } catch {}
  }
  $processes = @(Get-Process | Where-Object {
    $_.MainWindowHandle -ne 0 -and (
      $_.ProcessName -match 'Jianying|CapCut|VideoFusion' -or
      ($baseName -and $_.ProcessName -eq $baseName)
    )
  })
  if ($baseName) {
    $exact = $processes | Where-Object { $_.ProcessName -eq $baseName } | Select-Object -First 1
    if ($exact) { return $exact }
  }
  return $processes | Select-Object -First 1
}

function Get-RootElement {
  $p = Get-TargetProcess
  if (-not $p) { throw 'Jianying/CapCut process window not found' }
  [Win32DraftOpen]::ShowWindow($p.MainWindowHandle, 3) | Out-Null
  [Win32DraftOpen]::SetForegroundWindow($p.MainWindowHandle) | Out-Null
  Start-Sleep -Milliseconds 500
  return [System.Windows.Automation.AutomationElement]::FromHandle($p.MainWindowHandle)
}

function Get-WindowRect {
  $p = Get-TargetProcess
  if (-not $p) { throw 'Jianying/CapCut process window not found' }
  $rect = New-Object Win32DraftOpen+RECT
  if (-not [Win32DraftOpen]::GetWindowRect($p.MainWindowHandle, [ref]$rect)) {
    throw 'Jianying/CapCut window bounds unavailable'
  }
  return @{
    Left = $rect.Left
    Top = $rect.Top
    Width = [Math]::Max(1, $rect.Right - $rect.Left)
    Height = [Math]::Max(1, $rect.Bottom - $rect.Top)
  }
}

function Get-ElementName($element) {
  try { return [string]$element.Current.Name } catch { return '' }
}

function Find-BoundedNamedElement($root, [string[]]$names, [bool]$allowContains, [int]$timeoutMs, [int]$maxNodes) {
  $deadline = (Get-Date).AddMilliseconds([Math]::Max(300, $timeoutMs))
  $walkers = @(
    [System.Windows.Automation.TreeWalker]::ControlViewWalker,
    [System.Windows.Automation.TreeWalker]::RawViewWalker
  )
  foreach ($walker in $walkers) {
    $queue = New-Object System.Collections.Queue
    $child = $walker.GetFirstChild($root)
    while ($child) {
      $queue.Enqueue($child)
      $child = $walker.GetNextSibling($child)
    }
    $visited = 0
    while ($queue.Count -gt 0 -and $visited -lt $maxNodes -and (Get-Date) -lt $deadline) {
      $element = $queue.Dequeue()
      $visited += 1
      $name = Get-ElementName $element
      if (-not [string]::IsNullOrWhiteSpace($name)) {
        foreach ($candidate in $names) {
          if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
          if ($name -eq $candidate) { return $element }
          if ($allowContains -and $name.Contains($candidate)) {
            $containsMatch = $element
          }
        }
      }
      $child = $walker.GetFirstChild($element)
      while ($child -and $visited + $queue.Count -lt $maxNodes) {
        $queue.Enqueue($child)
        $child = $walker.GetNextSibling($child)
      }
    }
  }
  if ($containsMatch) { return $containsMatch }
  return $null
}

function Find-ExactNamedElement($root, [string[]]$names) {
  return Find-BoundedNamedElement $root $names $false 1200 420
}

function Find-ContainsNamedElement($root, [string[]]$names, [int]$timeoutMs, [int]$maxNodes) {
  return Find-BoundedNamedElement $root $names $true $timeoutMs $maxNodes
}

function Find-NamedElement($root, [string[]]$names, [bool]$allowContains) {
  $element = Find-ExactNamedElement $root $names
  if ($element -or -not $allowContains) { return $element }
  return Find-ContainsNamedElement $root $names 2500 900
}

function Test-Editor($root) {
  if (Find-ContainsNamedElement $root @(
    'VETreeMainCellItem:',
    'VETreeSubCellItem:',
    'VECollectTitleView:',
    'currentProgress',
    'totalProgress',
    'MTLSText:'
  ) 1800 900) {
    return $true
  }
  $hasEditorChrome = [bool](Find-ContainsNamedElement $root @(
    '播放器',
    '草稿参数',
    '导出',
    'Export',
    'Player'
  ) 1200 700)
  $hasToolTabs = [bool](Find-ContainsNamedElement $root @(
    '媒体',
    '音频',
    '文本',
    '字幕',
    'Media',
    'Audio',
    'Text',
    'Captions',
    'Subtitles'
  ) 1200 700)
  return $hasEditorChrome -and $hasToolTabs
}

function Test-EditorReady {
  try {
    $p = Get-TargetProcess
    if ($p -and $p.MainWindowTitle -and $p.MainWindowTitle.Contains($draftName)) { return $true }
  } catch {}
  try {
    $root = Get-RootElement
    return Test-Editor $root
  } catch {
    return $false
  }
}

function Click-Element($element, [int]$clickCount) {
  $scrollPattern = $null
  try {
    if ($element.TryGetCurrentPattern([System.Windows.Automation.ScrollItemPattern]::Pattern, [ref]$scrollPattern)) {
      $scrollPattern.ScrollIntoView()
      Start-Sleep -Milliseconds 200
    }
  } catch {}
  $invokePattern = $null
  if ($clickCount -le 1) {
    try {
      if ($element.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$invokePattern)) {
        $invokePattern.Invoke()
        return
      }
    } catch {}
  }
  $rect = $element.Current.BoundingRectangle
  if ($rect.IsEmpty -or $rect.Width -le 0 -or $rect.Height -le 0) {
    throw 'Target UI element has no usable screen bounds'
  }
  $x = [int]($rect.Left + ($rect.Width / 2))
  $y = [int]($rect.Top + ($rect.Height / 2))
  Click-Point $x $y $clickCount
}

function Click-Point([int]$x, [int]$y, [int]$clickCount) {
  [Win32DraftOpen]::SetCursorPos($x, $y) | Out-Null
  for ($i = 0; $i -lt [Math]::Max(1, $clickCount); $i++) {
    [Win32DraftOpen]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
    [Win32DraftOpen]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 160
  }
}

function Click-WindowRatio([double]$xRatio, [double]$yRatio, [int]$clickCount) {
  $rect = Get-WindowRect
  $x = [int]($rect.Left + ($rect.Width * $xRatio))
  $y = [int]($rect.Top + ($rect.Height * $yRatio))
  Click-Point $x $y $clickCount
}

function Open-DraftElement($element) {
  $scrollPattern = $null
  try {
    if ($element.TryGetCurrentPattern([System.Windows.Automation.ScrollItemPattern]::Pattern, [ref]$scrollPattern)) {
      $scrollPattern.ScrollIntoView()
      Start-Sleep -Milliseconds 250
    }
  } catch {}
  $rect = $element.Current.BoundingRectangle
  if ($rect.IsEmpty -or $rect.Width -le 0 -or $rect.Height -le 0) {
    throw 'Draft title UI element has no usable screen bounds'
  }
  $centerX = [int]($rect.Left + ($rect.Width / 2))
  $points = @(
    @($centerX, [int]($rect.Top + ($rect.Height / 2))),
    @($centerX, [int]([Math]::Max(0, $rect.Top - 55))),
    @($centerX, [int]([Math]::Max(0, $rect.Top - 85)))
  )
  foreach ($point in $points) {
    Click-Point ([int]$point[0]) ([int]$point[1]) 2
    Start-Sleep -Milliseconds 1200
    if (Test-EditorReady) { return $true }
  }
  return $false
}

function Wait-ForDraftTitle([int]$seconds) {
  $deadline = (Get-Date).AddSeconds([Math]::Max(1, $seconds))
  $draftNames = @("HomePageDraftTitle:$draftName", $draftName)
  while ((Get-Date) -lt $deadline) {
    $root = Get-RootElement
    $element = Find-NamedElement $root $draftNames $true
    if ($element) { return $element }
    Start-Sleep -Milliseconds 500
  }
  return $null
}

function Wait-ForEditor([int]$seconds = 12) {
  $deadline = (Get-Date).AddSeconds([Math]::Max(1, $seconds))
  while ((Get-Date) -lt $deadline) {
    if (Test-EditorReady) { return $true }
    Start-Sleep -Milliseconds 700
  }
  return $false
}

function Try-OpenNewestDraftByWindowClick {
  Write-Output 'stage=window-click-fallback'
  [void](Get-RootElement)
  $homePoints = @(
    @(0.052, 0.305),
    @(0.060, 0.245),
    @(0.045, 0.360)
  )
  foreach ($point in $homePoints) {
    Click-WindowRatio ([double]$point[0]) ([double]$point[1]) 1
    Start-Sleep -Milliseconds 700
  }
  $draftPoints = @(
    @(0.160, 0.340),
    @(0.210, 0.340),
    @(0.270, 0.340),
    @(0.160, 0.430),
    @(0.210, 0.430),
    @(0.270, 0.430)
  )
  foreach ($point in $draftPoints) {
    Write-Output ("stage=window-click-draft {0},{1}" -f $point[0], $point[1])
    Click-WindowRatio ([double]$point[0]) ([double]$point[1]) 2
    Start-Sleep -Milliseconds 1800
    if (Wait-ForEditor 4) { return $true }
  }
  return $false
}

$root = Get-RootElement
Write-Output 'stage=window-ready'
$draftElement = Find-NamedElement $root @("HomePageDraftTitle:$draftName", $draftName) $true
if (-not $draftElement) {
  Write-Output 'stage=draft-title-not-visible'
  $home = Find-ExactNamedElement $root @('首页', 'Home')
  if (-not $home) {
    $home = Find-ContainsNamedElement $root @('首页') 1800 600
  }
  if ($home) {
    Write-Output 'stage=click-home'
    Click-Element $home 1
    Start-Sleep -Milliseconds 1200
  }
  $draftElement = Wait-ForDraftTitle 4
}
if (-not $draftElement) {
  if (Try-OpenNewestDraftByWindowClick) {
    Write-Output 'opened-by-window-click'
    exit 0
  }
  throw "Could not find or open Jianying draft title: $draftName"
}
Write-Output 'stage=draft-title-found'
if (-not (Open-DraftElement $draftElement)) {
  if (Try-OpenNewestDraftByWindowClick) {
    Write-Output 'opened-by-window-click'
    exit 0
  }
  throw "Found draft title but Jianying editor did not become ready after clicking: $draftName"
}
Write-Output "opened-by-title"
`;
  try {
    return execFileSync('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
      timeout: 95000,
    }).trim();
  } catch (error) {
    const timedOut = error.killed || error.signal || /timed out|timeout|ETIMEDOUT/i.test(String(error.message || ''));
    const stdout = String(error.stdout || '').trim();
    const stderr = String(error.stderr || '').trim();
    const message = String(error.message || '').trim();
    const details = [];
    if (timedOut) details.push('Windows Jianying draft opening timed out while searching/clicking UI controls.');
    if (stderr) details.push(`PowerShell error:\n${stderr}`);
    if (stdout) details.push(`PowerShell progress:\n${stdout}`);
    if (!timedOut && message) details.push(message);
    fail(details.join('\n') || 'Windows Jianying draft opening failed.');
  }
}

function openFirstDraftCard(appPath, draftName = '') {
  if (process.platform === 'darwin') {
    activateJianying(appPath);
    macDismissJianyingStartupDialogs(appPath);
    if (!macNormalizeJianyingWindow(appPath)) {
      fail('Jianying home/editor window was not ready. Please grant Accessibility permission to AI Drama and keep the screen available during capture.');
    }
    const [x, y, w, h] = macFrontWindowBounds(appPath);
    if (!macClickStaticText(appPath, '首页')) {
      macMouseClick(
        Math.round(x + w * DEFAULTS.homeNavClickXRatio),
        Math.round(y + h * DEFAULTS.homeNavClickYRatio),
      );
    }
    sleep(2.5);
    if (macClickDraftTitle(appPath, draftName) && macWaitForEditor(appPath)) {
      return true;
    }
    if (draftName) {
      fail(`Could not open Jianying draft by title: ${draftName}`);
    }
    const candidates = [
      [DEFAULTS.draftCardClickXRatio, DEFAULTS.draftCardClickYRatio],
      [0.18, 0.50],
      [0.24, 0.50],
      [0.30, 0.50],
      [0.36, 0.50],
    ];
    for (const [clickXRatio, clickYRatio] of candidates) {
      const clickX = Math.round(x + w * clickXRatio);
      const clickY = Math.round(y + h * clickYRatio);
      macMouseClick(clickX, clickY, 2);
      if (macWaitForEditor(appPath, 8)) return true;
    }
    fail('Jianying draft editor did not open; refusing to capture the home page.');
  }
  if (process.platform === 'win32') {
    activateJianying(appPath);
    winOpenDraftByTitle(appPath, draftName);
    return true;
  }
  return false;
}

function psSingle(value) {
  return `'${String(value).replace(/'/g, "''")}'`;
}

function positiveWindowRect(rect) {
  const [x, y, w, h] = rect.map((value) => Math.round(Number(value)));
  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) {
    fail(`Invalid window bounds for screenshot: ${rect.join(',')}`);
  }
  return [x, y, w, h];
}

function captureScreenshot(output, options = {}) {
  fs.mkdirSync(path.dirname(output), { recursive: true });
  if (process.platform === 'darwin') {
    if (options.fullScreen) {
      execFileSync('screencapture', ['-x', output], { stdio: 'ignore' });
      return output;
    }
    if (options.appPath) activateJianying(options.appPath);
    const captureTarget = options.appPath ? macJianyingWindowCaptureTarget(options.appPath) : null;
    if (captureTarget?.windowId) {
      execFileSync('screencapture', ['-x', '-o', '-l', String(captureTarget.windowId), output], { stdio: 'ignore' });
      return output;
    }
    const [x, y, w, h] = positiveWindowRect(macFrontWindowBounds(options.appPath));
    execFileSync('screencapture', ['-x', '-R', `${x},${y},${w},${h}`, output], { stdio: 'ignore' });
    return output;
  }
  if (process.platform === 'win32') {
    const script = options.fullScreen ? `
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$graphics = [System.Drawing.Graphics]::FromImage($bmp)
$graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$bmp.Save(${psSingle(output)}, [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bmp.Dispose()
` : `
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32Capture {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
}
"@
[Win32Capture]::SetProcessDPIAware() | Out-Null
$p = Get-Process | Where-Object { $_.MainWindowHandle -ne 0 -and $_.ProcessName -match "Jianying|CapCut|VideoFusion" } | Select-Object -First 1
if (-not $p) { throw "Jianying/CapCut window not found" }
[Win32Capture]::ShowWindow($p.MainWindowHandle, 9) | Out-Null
[Win32Capture]::SetForegroundWindow($p.MainWindowHandle) | Out-Null
Start-Sleep -Milliseconds 300
$r = New-Object Win32Capture+RECT
[Win32Capture]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
$width = [Math]::Max(1, $r.Right - $r.Left)
$height = [Math]::Max(1, $r.Bottom - $r.Top)
$bmp = New-Object System.Drawing.Bitmap $width, $height
$graphics = [System.Drawing.Graphics]::FromImage($bmp)
$graphics.CopyFromScreen($r.Left, $r.Top, 0, 0, $bmp.Size)
$bmp.Save(${psSingle(output)}, [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bmp.Dispose()
`;
    execFileSync('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script], { stdio: 'ignore' });
    return output;
  }
  fail(`Screenshot capture is not implemented for platform: ${process.platform}`);
}

function createProject(args) {
  const ffmpegBin = args.ffmpeg || 'ffmpeg';
  const ffprobeBin = args.ffprobe || ffprobePathForFfmpeg(ffmpegBin);
  const video = resolveExistingFile(args.video, 'Video');
  const srt = args.srt ? resolveExistingFile(args.srt, 'SRT') : null;
  const bgmFiles = args.bgm.map((file, index) => resolveExistingFile(file, `BGM #${index + 1}`));
  const draftRoot = path.resolve(args.draftRoot || defaultDraftRoot());
  if (!existsDir(draftRoot)) fail(`Jianying draft root not found: ${draftRoot}`);
  const rootFile = path.join(draftRoot, 'root_meta_info.json');
  if (!fs.existsSync(rootFile)) fail(`root_meta_info.json not found: ${rootFile}`);
  const templateDraft = findTemplateDraft(draftRoot, args.template);
  const draftName = sanitizeName(args.name || `${path.basename(video, path.extname(video))}_剪辑工程`);
  const draftDir = path.join(draftRoot, draftName);
  ensureInside(draftRoot, draftDir);
  if (fs.existsSync(draftDir)) {
    if (!args.overwrite) fail(`Draft exists: ${draftDir}; pass --overwrite`);
    fs.rmSync(draftDir, { recursive: true, force: true });
  }

  fs.cpSync(templateDraft, draftDir, { recursive: true });
  const resourceMediaDir = path.join(draftDir, 'Resources', 'media');
  const resourceAudioDir = path.join(draftDir, 'Resources', 'audio');
  emptyDirInside(draftDir, resourceMediaDir);
  emptyDirInside(draftDir, resourceAudioDir);

  const timestampUs = nowUs();
  const draftId = uuid();
  const videoInfo = mediaInfo(video, ffprobeBin);
  if (!videoInfo.width || !videoInfo.height || !videoInfo.durationUs) fail(`Video has no readable video stream: ${video}`);
  const rng = createRng(`${draftName}|${video}|${videoInfo.durationUs}|${videoInfo.width}x${videoInfo.height}`);
  const captions = parseSrt(srt, videoInfo.durationUs);
  const useSeparateDialogueAudio = videoInfo.hasAudio && captions.length > 0;
  const draftInfoFile = path.join(draftDir, 'draft_info.json');
  const draft = readJson(draftInfoFile);
  const baseVideo = clone(draft.materials?.videos?.[0]);
  const baseSegment = clone(draft.tracks?.find((track) => track.type === 'video')?.segments?.[0]);
  if (!baseVideo || !baseSegment) fail('Template draft needs at least one video material and one video segment');
  const baseExtras = {
    speeds: clone(draft.materials.speeds?.[0] || null),
    canvases: clone(draft.materials.canvases?.[0] || null),
    sound_channel_mappings: clone(draft.materials.sound_channel_mappings?.[0] || null),
    loudnesses: clone(draft.materials.loudnesses?.[0] || null),
    vocal_separations: clone(draft.materials.vocal_separations?.[0] || null),
  };
  resetMaterialBuckets(draft.materials, [
    'speeds',
    'canvases',
    'sound_channel_mappings',
    'loudnesses',
    'vocal_separations',
  ]);

  const ranges = splitRanges(videoInfo.durationUs, Number(args.clipCount || DEFAULTS.clipCount), rng);
  const splitClips = splitVideo({ source: video, outputDir: resourceMediaDir, ranges, ffmpegBin });
  const videoMaterials = [];
  const videoMetas = [];
  const videoExtraRefKeys = useSeparateDialogueAudio
    ? ['speeds', 'canvases']
    : [
      'speeds',
      'canvases',
      'sound_channel_mappings',
      'loudnesses',
      'vocal_separations',
    ];
  let speedEditCount = 0;
  const videoSegments = splitClips.map((clip, index) => {
    const materialId = uuid();
    const materialLocalId = localId();
    const clipInfo = mediaInfo(clip.output, ffprobeBin);
    const durationUs = clip.duration;
    const speed = speedForClip(index, rng);
    if (speed !== 1.0) speedEditCount += 1;
    const videoMaterial = {
      ...baseVideo,
      duration: clipInfo.durationUs || durationUs,
      has_audio: videoInfo.hasAudio && !useSeparateDialogueAudio,
      height: videoInfo.height,
      id: materialId,
      local_material_id: materialLocalId,
      material_name: clip.fileName,
      media_path: clip.output,
      path: clip.output,
      width: videoInfo.width,
    };
    videoMaterials.push(videoMaterial);
    videoMetas.push({
      durationUs,
      height: videoInfo.height,
      localMaterialId: materialLocalId,
      name: clip.fileName,
      size: fs.statSync(clip.output).size,
      width: videoInfo.width,
    });
    const extraRefs = makeExtraRefs(draft.materials, baseExtras, videoExtraRefKeys, (key, material) => {
      if (key === 'speeds') {
        material.speed = speed;
        material.mode = 0;
        material.curve_speed = null;
      }
    });
    return makeVideoSegment(baseSegment, materialId, {
      start: clip.start,
      duration: clip.duration,
    }, index, extraRefs, speed);
  });

  const bgmVolume = Number(args.bgmVolume ?? DEFAULTS.bgmVolume);
  const audioMaterials = [];
  const bgmAudioMaterials = [];
  const audioMetas = [];
  const audioInfos = [];
  let dialogueAudioTrack = null;
  if (useSeparateDialogueAudio) {
    const dialogueAudio = extractDialogueAudio({ source: video, outputDir: resourceAudioDir, ffmpegBin });
    const dialogueInfo = mediaInfo(dialogueAudio.output, ffprobeBin);
    const materialId = uuid();
    const materialLocalId = localId();
    const dialogueMaterial = makeAudioMaterial({
      id: materialId,
      localMaterialId: materialLocalId,
      fileName: dialogueAudio.fileName,
      durationUs: dialogueInfo.durationUs || videoInfo.durationUs,
      filePath: dialogueAudio.output,
    });
    audioMaterials.push(dialogueMaterial);
    audioMetas.push({
      durationUs: dialogueMaterial.duration,
      localMaterialId: materialLocalId,
      name: dialogueAudio.fileName,
      size: fs.statSync(dialogueAudio.output).size,
    });
    dialogueAudioTrack = {
      name: DIALOGUE_AUDIO_TRACK_NAME,
      segments: captions.map((caption) => {
        const duration = Math.min(caption.duration, Math.max(0, dialogueMaterial.duration - caption.start));
        if (duration <= 0) return null;
        const extraRefs = makeExtraRefs(draft.materials, baseExtras, [
          'speeds',
          'sound_channel_mappings',
          'loudnesses',
          'vocal_separations',
        ]);
        return makeAudioSegment(
          dialogueMaterial.id,
          caption.start,
          caption.start,
          duration,
          extraRefs,
          1.0,
        );
      }).filter(Boolean),
    };
  }
  bgmFiles.forEach((file, index) => {
    const info = mediaInfo(file, ffprobeBin);
    audioInfos.push(info);
    const audioName = makeAudioDisplayName(file, index);
    const audioPath = path.join(resourceAudioDir, audioName);
    fs.copyFileSync(file, audioPath);
    const materialId = uuid();
    const materialLocalId = localId();
    const audioMaterial = makeAudioMaterial({
      id: materialId,
      localMaterialId: materialLocalId,
      fileName: audioName,
      durationUs: info.durationUs,
      filePath: audioPath,
    });
    audioMaterials.push(audioMaterial);
    bgmAudioMaterials.push(audioMaterial);
    audioMetas.push({
      durationUs: info.durationUs,
      localMaterialId: materialLocalId,
      name: audioName,
      size: fs.statSync(audioPath).size,
    });
  });
  const audioPlans = makeAudioPlan({ bgmFiles, audioInfos, totalUs: videoInfo.durationUs, rng });
  const audioTracks = audioPlans
    .map((plans, trackIndex) => ({
      name: BGM_AUDIO_TRACK_NAMES[trackIndex] || `A${trackIndex + 2} 情绪配乐`,
      segments: plans.map((plan, index) => {
        const extraRefs = makeExtraRefs(draft.materials, baseExtras, [
          'speeds',
          'sound_channel_mappings',
          'loudnesses',
          'vocal_separations',
        ]);
        return makeAudioSegment(
          bgmAudioMaterials[plan.audioIndex].id,
          plan.sourceStart,
          plan.start,
          plan.duration,
          extraRefs,
          Math.max(0.16, Math.min(0.5, bgmVolume + (trackIndex === 1 ? 0.04 : 0))),
        );
      }),
    }))
    .filter((track) => track.segments.length);

  const captionScale = Number(args.captionScale ?? DEFAULTS.captionScale);
  const captionTextSize = Number(args.captionTextSize ?? DEFAULTS.captionTextSize);
  const textMaterials = [];
  const textSegments = captions.map((caption, index) => {
    const material = makeTextMaterial({
      id: uuid(),
      text: caption.text,
      textSize: captionTextSize,
    });
    textMaterials.push(material);
    return makeTextSegment(material.id, caption, index, captionScale);
  });
  const overlayVideoSegments = makeOverlayVideoSegments({
    baseSegment,
    baseExtras,
    draftMaterials: draft.materials,
    rng,
    sourceSegments: videoSegments,
    totalUs: videoInfo.durationUs,
  });
  const videoTracks = [
    { name: VIDEO_TRACK_NAMES[0], segments: videoSegments },
    ...(overlayVideoSegments.length ? [{ name: VIDEO_TRACK_NAMES[1], segments: overlayVideoSegments }] : []),
  ];
  const subtitleTracks = namedSegmentTracks({
    segments: textSegments,
    names: SUBTITLE_TRACK_NAMES,
    count: 1,
  });
  const auxTracks = [];
  const allAudioTracks = [
    ...(dialogueAudioTrack?.segments.length ? [dialogueAudioTrack] : []),
    ...audioTracks,
  ];

  draft.id = draftId;
  draft.name = draftName;
  draft.create_time = timestampUs;
  draft.update_time = timestampUs;
  draft.duration = videoInfo.durationUs;
  draft.materials.videos = videoMaterials;
  draft.materials.audios = audioMaterials;
  draft.materials.texts = textMaterials;
  const draftTracks = [];
  videoTracks.forEach((track, index) => {
    draftTracks.push(makeTrack('video', assignTrackRenderIndex(track.segments, index), track.name));
  });
  allAudioTracks.forEach((track, index) => {
    draftTracks.push(makeTrack('audio', assignTrackRenderIndex(track.segments, index), track.name));
  });
  let textTrackRenderIndex = 0;
  subtitleTracks.forEach((track) => {
    draftTracks.push(makeTrack('text', assignTrackRenderIndex(track.segments, textTrackRenderIndex), track.name));
    textTrackRenderIndex += 1;
  });
  auxTracks.forEach((track) => {
    draftTracks.push(makeTrack('text', assignTrackRenderIndex(track.segments, textTrackRenderIndex), track.name));
    textTrackRenderIndex += 1;
  });
  draft.tracks = draftTracks;
  draft.relationships = [];
  const missingRefs = validateRefs(draft);
  if (missingRefs.length) fail(`Draft has missing material refs: ${missingRefs.join(', ')}`);
  writeJson(draftInfoFile, draft);

  updateDraftMeta(draftDir, draftName, draftId, videoMetas, audioMetas, timestampUs);
  updateVirtualStore(draftDir, videoMetas, audioMetas, timestampUs);

  const rootBackup = `${rootFile}.codex-backup-${new Date().toISOString().replace(/[-:TZ.]/g, '').slice(0, 14)}`;
  const draftMaterialSize = [...videoMetas, ...audioMetas].reduce((sum, item) => sum + item.size, 0);
  fs.copyFileSync(rootFile, rootBackup);
  upsertRootEntry(rootFile, {
    draft_cloud_last_action_download: false,
    draft_cloud_purchase_info: '',
    draft_cloud_template_id: '',
    draft_cloud_tutorial_info: '',
    draft_cloud_videocut_purchase_info: '',
    draft_cover: path.join(draftDir, 'draft_cover.jpg'),
    draft_fold_path: draftDir,
    draft_id: draftId,
    draft_is_ai_shorts: false,
    draft_is_invisible: false,
    draft_json_file: draftInfoFile,
    draft_name: draftName,
    draft_new_version: '',
    draft_root_path: draftRoot,
    draft_timeline_materials_size: draftMaterialSize,
    draft_type: '',
    tm_draft_cloud_completed: '',
    tm_draft_cloud_modified: 0,
    tm_draft_create: timestampUs,
    tm_draft_modified: timestampUs,
    tm_draft_removed: 0,
    tm_duration: videoInfo.durationUs,
  }, args.overwrite);

  const outputDir = path.resolve(args.outputDir || path.join(path.dirname(video), `${draftName}_proof`));
  fs.mkdirSync(outputDir, { recursive: true });
  const audit = {
    success: true,
    platform: process.platform,
    draft_name: draftName,
    draft_dir: draftDir,
    draft_root: draftRoot,
    template_draft: templateDraft,
    video,
    srt,
    bgm: bgmFiles,
    output_dir: outputDir,
    result_path: path.join(outputDir, 'jianying_project_result.json'),
    duration_microseconds: videoInfo.durationUs,
    width: videoInfo.width,
    height: videoInfo.height,
    root_backup: rootBackup,
    tracks: {
      video_segments: videoSegments.length,
      video_tracks: videoTracks.length,
      overlay_video_segments: overlayVideoSegments.length,
      audio_segments: allAudioTracks.reduce((sum, track) => sum + track.segments.length, 0),
      dialogue_audio_segments: dialogueAudioTrack?.segments.length || 0,
      background_audio_segments: audioTracks.reduce((sum, track) => sum + track.segments.length, 0),
      text_segments: textSegments.length,
      subtitle_text_tracks: subtitleTracks.length,
      auxiliary_text_segments: auxTracks.reduce((sum, track) => sum + track.segments.length, 0),
      audio_tracks: allAudioTracks.length,
      auxiliary_text_tracks: auxTracks.length,
      total_tracks: draft.tracks.length,
    },
    materials: {
      videos: videoMaterials.length,
      audios: audioMaterials.length,
      texts: textMaterials.length,
    },
    edits: {
      speed_edits: speedEditCount,
      uneven_video_segments: true,
    },
    caption: {
      scale: captionScale,
      text_size: captionTextSize,
    },
    screenshot_path: null,
    warnings: [],
  };

  writeJson(path.join(draftDir, 'codex_audit.json'), audit);
  return audit;
}

function postCreateAutomation(args, audit) {
  let draftOpened = !args.openDraft;
  if (args.closeExisting) {
    closeExistingJianying();
    sleep(1.5);
  }
  const appPath = findJianyingApp(args.jianyingApp);
  if ((args.open || args.openDraft) && !openJianying(appPath)) {
    audit.warnings.push('Jianying app was not found; draft was created but not opened.');
  }
  if (args.open || args.openDraft) sleep(Number(args.homepageDelay ?? DEFAULTS.homepageDelay));
  if (args.openDraft) {
    try {
      openFirstDraftCard(appPath, audit.draft_name);
      draftOpened = true;
      sleep(Number(args.editorDelay ?? DEFAULTS.editorDelay));
    } catch (error) {
      audit.warnings.push(`Could not open newest draft card automatically: ${error.message}`);
    }
  }
  if (args.capture) {
    if (args.openDraft && !draftOpened) {
      audit.warnings.push('Screenshot skipped because Jianying editor did not open.');
      return;
    }
    if (args.open || args.openDraft) activateJianying(appPath);
    sleep(Number(args.captureDelay ?? DEFAULTS.captureDelay));
    const screenshot = path.resolve(args.screenshot || path.join(audit.output_dir, `${audit.draft_name}_工程图.png`));
    try {
      audit.screenshot_mode = args.fullScreenCapture ? 'full_screen' : 'app_window';
      audit.screenshot_path = captureScreenshot(screenshot, {
        appPath,
        fullScreen: args.fullScreenCapture,
      });
    } catch (error) {
      audit.warnings.push(`Screenshot capture failed: ${error.message}`);
    }
  }
}

function main() {
  const args = parseArgs(process.argv);
  if (args.help) {
    process.stdout.write(HELP.trimStart());
    return;
  }
  if (!args.video) fail('--video is required');
  const audit = createProject(args);
  postCreateAutomation(args, audit);
  writeJson(audit.result_path, audit);
  writeJson(path.join(audit.draft_dir, 'codex_audit.json'), audit);
  process.stdout.write(`${JSON.stringify(audit, null, 2)}\n`);
}

try {
  main();
} catch (error) {
  process.stderr.write(`${error.stack || error.message}\n`);
  process.exit(1);
}
