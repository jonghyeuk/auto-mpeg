/**
 * 기본 설정
 */

export const defaultConfig = {
  // API Keys (환경 변수에서 로드)
  anthropicApiKey: process.env.ANTHROPIC_API_KEY,
  openaiApiKey: process.env.OPENAI_API_KEY,

  // 출력 설정
  output: {
    baseDir: process.env.OUTPUT_DIR || 'outputs',
    keepTemp: process.env.KEEP_TEMP_FILES === 'true',
  },

  // 품질 검토
  qualityCheck: {
    enabled: process.env.QUALITY_CHECK_ENABLED !== 'false',
    minScore: parseInt(process.env.QUALITY_MIN_SCORE || '70', 10),
  },

  // 영상 설정
  video: {
    defaultResolution: (process.env.VIDEO_RESOLUTION as '1920x1080' | '1280x720') || '1920x1080',
    defaultFps: parseInt(process.env.VIDEO_FPS || '30', 10),
    burnSubtitles: process.env.BURN_SUBTITLES !== 'false',
  },

  // TTS 설정
  tts: {
    provider: (process.env.TTS_PROVIDER as 'openai' | 'elevenlabs' | 'google') || 'openai',
    voiceId: process.env.TTS_VOICE_ID,
    language: process.env.TTS_LANGUAGE || 'ko-KR',
    speed: parseFloat(process.env.TTS_SPEED || '1.0'),
  },

  // 로깅
  logging: {
    level: process.env.LOG_LEVEL || 'info',
  },
};

export type Config = typeof defaultConfig;
