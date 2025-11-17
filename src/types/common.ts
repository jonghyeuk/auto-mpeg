/**
 * 공통 타입 정의
 */

/**
 * 작업 상태
 */
export enum JobStatus {
  PENDING = 'pending',
  IN_PROGRESS = 'in_progress',
  COMPLETED = 'completed',
  FAILED = 'failed',
}

/**
 * 모듈 타입
 */
export enum ModuleType {
  CONTENT_INTAKE = 'content_intake',
  CONTENT_ANALYZER = 'content_analyzer',
  PLANNER = 'planner',
  SCRIPT_GENERATOR = 'script_generator',
  TTS = 'tts',
  SUBTITLE_GENERATOR = 'subtitle_generator',
  VIDEO_COMPOSER = 'video_composer',
  THUMBNAIL_GENERATOR = 'thumbnail_generator',
  QUALITY_REVIEW = 'quality_review',
}

/**
 * 로그 레벨
 */
export enum LogLevel {
  DEBUG = 'debug',
  INFO = 'info',
  WARN = 'warn',
  ERROR = 'error',
}

/**
 * 작업 컨텍스트
 */
export interface JobContext {
  jobId: string;
  status: JobStatus;
  createdAt: Date;
  updatedAt: Date;
  outputPath: string;
  metadata: Record<string, any>;
}

/**
 * 모듈 실행 결과
 */
export interface ModuleResult<T = any> {
  success: boolean;
  data?: T;
  error?: Error;
  timestamp: Date;
  moduleType: ModuleType;
}

/**
 * 에러 타입
 */
export class ModuleError extends Error {
  constructor(
    public moduleType: ModuleType,
    message: string,
    public originalError?: Error
  ) {
    super(message);
    this.name = 'ModuleError';
  }
}
