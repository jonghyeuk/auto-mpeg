/**
 * 모듈별 입출력 타입 정의
 */

/**
 * 1. 콘텐츠 인입 모듈
 */
export interface ContentIntakeInput {
  source: string; // URL 또는 텍스트
  sourceType: 'url' | 'text';
}

export interface ContentIntakeOutput {
  cleanedText: string;
  originalSource: string;
  sourceType: 'url' | 'text';
  metadata: {
    title?: string;
    author?: string;
    publishedDate?: string;
    extractedAt: Date;
  };
}

/**
 * 2. 콘텐츠 분석기
 */
export interface ContentAnalyzerInput {
  text: string;
  metadata?: Record<string, any>;
}

export enum ContentType {
  INFORMATIONAL = 'informational',
  STORYTELLING = 'storytelling',
  TUTORIAL = 'tutorial',
  REVIEW = 'review',
  NEWS = 'news',
  OPINION = 'opinion',
}

export enum ContentTone {
  FORMAL = 'formal',
  CASUAL = 'casual',
  FRIENDLY = 'friendly',
  PROFESSIONAL = 'professional',
  ENTHUSIASTIC = 'enthusiastic',
  NEUTRAL = 'neutral',
}

export interface ContentAnalyzerOutput {
  contentType: ContentType;
  tone: ContentTone;
  structure: {
    sections: Array<{
      heading?: string;
      content: string;
      startIndex: number;
      endIndex: number;
    }>;
  };
  keywords: string[];
  coreMessage: string;
  estimatedReadingTime: number; // 분 단위
  complexity: 'simple' | 'moderate' | 'complex';
}

/**
 * 3. LLM 플래너
 */
export interface PlannerInput {
  contentAnalysis: ContentAnalyzerOutput;
  originalText: string;
  targetLength?: number; // 초 단위, 선택 사항
}

export interface VideoPlan {
  targetDuration: number; // 초 단위
  structure: Array<{
    sectionType: 'hook' | 'introduction' | 'main_content' | 'summary' | 'conclusion' | 'cta';
    estimatedDuration: number; // 초 단위
    objectives: string[];
  }>;
  tone: ContentTone;
  pacing: 'slow' | 'medium' | 'fast';
  visualStyle: 'static' | 'slideshow' | 'dynamic';
}

export type PlannerOutput = VideoPlan;

/**
 * 4. 스크립트 생성기
 */
export interface ScriptGeneratorInput {
  originalText: string;
  plan: VideoPlan;
  contentAnalysis: ContentAnalyzerOutput;
}

export interface ScriptLine {
  id: string;
  sectionId: string;
  text: string;
  order: number;
  startTime?: number; // TTS 모듈이 채움
  endTime?: number; // TTS 모듈이 채움
  visualCue?: string; // 시각적 힌트 (키워드 등)
}

export interface ScriptSection {
  id: string;
  type: 'hook' | 'introduction' | 'main_content' | 'summary' | 'conclusion' | 'cta';
  title?: string;
  lines: ScriptLine[];
  order: number;
}

export interface ScriptGeneratorOutput {
  sections: ScriptSection[];
  totalEstimatedDuration: number;
  metadata: {
    wordCount: number;
    sentenceCount: number;
    generatedAt: Date;
  };
}

/**
 * 5. TTS 모듈
 */
export interface TTSInput {
  script: ScriptGeneratorOutput;
  voice?: {
    provider?: 'openai' | 'elevenlabs' | 'google' | 'aws';
    voiceId?: string;
    language?: string;
    speed?: number;
  };
}

export interface AudioSegment {
  lineId: string;
  filePath: string;
  duration: number; // 초 단위
  startTime: number; // 전체 오디오에서의 시작 시간
  endTime: number; // 전체 오디오에서의 종료 시간
}

export interface TTSOutput {
  audioSegments: AudioSegment[];
  masterAudioPath: string;
  totalDuration: number;
  scriptWithTimestamps: ScriptGeneratorOutput; // 타임스탬프가 업데이트된 스크립트
}

/**
 * 6. 자막 생성기
 */
export interface SubtitleGeneratorInput {
  scriptWithTimestamps: ScriptGeneratorOutput;
  format?: 'srt' | 'vtt' | 'ass';
}

export interface SubtitleEntry {
  index: number;
  startTime: string; // SRT 형식: "00:00:01,000"
  endTime: string;
  text: string;
}

export interface SubtitleGeneratorOutput {
  subtitlePath: string;
  format: 'srt' | 'vtt' | 'ass';
  entries: SubtitleEntry[];
}

/**
 * 7. 영상 합성 모듈
 */
export interface VisualAsset {
  type: 'image' | 'video';
  path: string;
  startTime: number;
  endTime: number;
  transition?: 'fade' | 'slide' | 'none';
}

export interface VideoComposerInput {
  audioPath: string;
  totalDuration: number;
  subtitlePath?: string;
  visualAssets?: VisualAsset[];
  scriptWithTimestamps: ScriptGeneratorOutput;
  options?: {
    resolution?: '1920x1080' | '1280x720' | '3840x2160';
    fps?: number;
    burnSubtitles?: boolean;
    backgroundColor?: string;
  };
}

export interface VideoComposerOutput {
  videoPath: string;
  videoPathClean?: string; // 자막 없는 버전
  resolution: string;
  duration: number;
  fileSize: number; // bytes
}

/**
 * 8. 썸네일 생성 모듈
 */
export interface ThumbnailGeneratorInput {
  title: string;
  keywords: string[];
  contentType: ContentType;
  style?: 'minimalist' | 'bold' | 'professional' | 'creative';
}

export interface ThumbnailGeneratorOutput {
  thumbnailPath: string;
  width: number;
  height: number;
  format: 'png' | 'jpg';
}

/**
 * 9. 품질 검토 모듈
 */
export interface QualityReviewInput {
  originalText: string;
  generatedScript: ScriptGeneratorOutput;
  contentAnalysis: ContentAnalyzerOutput;
}

export interface QualityIssue {
  severity: 'low' | 'medium' | 'high' | 'critical';
  category: 'factual_error' | 'omission' | 'exaggeration' | 'tone_mismatch' | 'other';
  sectionId?: string;
  lineId?: string;
  description: string;
  suggestion?: string;
}

export interface QualityReviewOutput {
  passed: boolean;
  score: number; // 0-100
  issues: QualityIssue[];
  recommendation: 'approve' | 'revise' | 'reject';
  reviewedAt: Date;
}

/**
 * 최종 산출물 패키지
 */
export interface OutputPackage {
  jobId: string;
  paths: {
    video: string;
    videoClean?: string;
    subtitles: string;
    audio: string;
    script: string;
    thumbnail: string;
    metadata: string;
  };
  metadata: {
    originalSource: string;
    title?: string;
    duration: number;
    createdAt: Date;
    processingTime: number; // 초 단위
  };
}
