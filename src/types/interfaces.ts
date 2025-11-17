/**
 * 모듈 인터페이스 정의
 */

import { ModuleResult } from './common';
import {
  ContentIntakeInput,
  ContentIntakeOutput,
  ContentAnalyzerInput,
  ContentAnalyzerOutput,
  PlannerInput,
  PlannerOutput,
  ScriptGeneratorInput,
  ScriptGeneratorOutput,
  TTSInput,
  TTSOutput,
  SubtitleGeneratorInput,
  SubtitleGeneratorOutput,
  VideoComposerInput,
  VideoComposerOutput,
  ThumbnailGeneratorInput,
  ThumbnailGeneratorOutput,
  QualityReviewInput,
  QualityReviewOutput,
} from './modules';

/**
 * 기본 모듈 인터페이스
 */
export interface BaseModule<TInput, TOutput> {
  execute(input: TInput): Promise<ModuleResult<TOutput>>;
  validate(input: TInput): Promise<boolean>;
  getName(): string;
}

/**
 * 1. 콘텐츠 인입 모듈 인터페이스
 */
export interface IContentIntakeModule
  extends BaseModule<ContentIntakeInput, ContentIntakeOutput> {
  extractFromUrl(url: string): Promise<ContentIntakeOutput>;
  cleanText(text: string): Promise<string>;
}

/**
 * 2. 콘텐츠 분석기 인터페이스
 */
export interface IContentAnalyzerModule
  extends BaseModule<ContentAnalyzerInput, ContentAnalyzerOutput> {
  analyzeStructure(text: string): Promise<ContentAnalyzerOutput['structure']>;
  extractKeywords(text: string): Promise<string[]>;
  detectTone(text: string): Promise<ContentAnalyzerOutput['tone']>;
}

/**
 * 3. 플래너 인터페이스
 */
export interface IPlannerModule extends BaseModule<PlannerInput, PlannerOutput> {
  createVideoPlan(input: PlannerInput): Promise<PlannerOutput>;
  optimizePlan(plan: PlannerOutput): Promise<PlannerOutput>;
}

/**
 * 4. 스크립트 생성기 인터페이스
 */
export interface IScriptGeneratorModule
  extends BaseModule<ScriptGeneratorInput, ScriptGeneratorOutput> {
  generateScript(input: ScriptGeneratorInput): Promise<ScriptGeneratorOutput>;
  refineSection(sectionId: string, feedback: string): Promise<ScriptGeneratorOutput>;
}

/**
 * 5. TTS 모듈 인터페이스
 */
export interface ITTSModule extends BaseModule<TTSInput, TTSOutput> {
  synthesizeSpeech(text: string, options?: any): Promise<{ path: string; duration: number }>;
  mergeAudioFiles(filePaths: string[], outputPath: string): Promise<string>;
  getAudioDuration(filePath: string): Promise<number>;
}

/**
 * 6. 자막 생성기 인터페이스
 */
export interface ISubtitleGeneratorModule
  extends BaseModule<SubtitleGeneratorInput, SubtitleGeneratorOutput> {
  generateSRT(input: SubtitleGeneratorInput): Promise<string>;
  generateVTT(input: SubtitleGeneratorInput): Promise<string>;
}

/**
 * 7. 영상 합성 모듈 인터페이스
 */
export interface IVideoComposerModule
  extends BaseModule<VideoComposerInput, VideoComposerOutput> {
  composeVideo(input: VideoComposerInput): Promise<VideoComposerOutput>;
  burnSubtitles(videoPath: string, subtitlePath: string): Promise<string>;
  addAudioToVideo(videoPath: string, audioPath: string): Promise<string>;
}

/**
 * 8. 썸네일 생성 모듈 인터페이스
 */
export interface IThumbnailGeneratorModule
  extends BaseModule<ThumbnailGeneratorInput, ThumbnailGeneratorOutput> {
  generateThumbnail(input: ThumbnailGeneratorInput): Promise<ThumbnailGeneratorOutput>;
  applyTemplate(
    templatePath: string,
    text: string,
    outputPath: string
  ): Promise<ThumbnailGeneratorOutput>;
}

/**
 * 9. 품질 검토 모듈 인터페이스
 */
export interface IQualityReviewModule
  extends BaseModule<QualityReviewInput, QualityReviewOutput> {
  reviewScript(input: QualityReviewInput): Promise<QualityReviewOutput>;
  checkFactualAccuracy(original: string, generated: string): Promise<boolean>;
}
