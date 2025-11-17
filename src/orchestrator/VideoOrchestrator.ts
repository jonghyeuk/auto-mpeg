/**
 * 비디오 오케스트레이터
 * 모든 모듈을 조율하여 블로그 글에서 영상까지 전체 파이프라인 실행
 */

import * as fs from 'fs/promises';
import * as path from 'path';
import { v4 as uuidv4 } from 'uuid';
import {
  JobContext,
  JobStatus,
  OutputPackage,
  ContentIntakeInput,
  ModuleError,
} from '@/types';

import { ContentIntakeModule } from '@/modules/content-intake';
import { ContentAnalyzerModule } from '@/modules/content-analyzer';
import { PlannerModule } from '@/modules/planner';
import { ScriptGeneratorModule } from '@/modules/script-generator';
import { TTSModule } from '@/modules/tts';
import { SubtitleGeneratorModule } from '@/modules/subtitle-generator';
import { VideoComposerModule } from '@/modules/video-composer';
import { ThumbnailGeneratorModule } from '@/modules/thumbnail-generator';
import { QualityReviewModule } from '@/modules/quality-review';

export interface OrchestratorConfig {
  outputDir?: string;
  qualityCheckEnabled?: boolean;
  targetVideoLength?: number; // 초 단위
}

export class VideoOrchestrator {
  private config: OrchestratorConfig;

  // 모듈 인스턴스
  private contentIntake: ContentIntakeModule;
  private contentAnalyzer: ContentAnalyzerModule;
  private planner: PlannerModule;
  private scriptGenerator: ScriptGeneratorModule;
  private tts: TTSModule;
  private subtitleGenerator: SubtitleGeneratorModule;
  private videoComposer: VideoComposerModule;
  private thumbnailGenerator: ThumbnailGeneratorModule;
  private qualityReview: QualityReviewModule;

  constructor(config: OrchestratorConfig = {}) {
    this.config = {
      outputDir: config.outputDir || path.join(process.cwd(), 'outputs'),
      qualityCheckEnabled: config.qualityCheckEnabled ?? true,
      targetVideoLength: config.targetVideoLength,
    };

    // 모듈 초기화
    this.contentIntake = new ContentIntakeModule();
    this.contentAnalyzer = new ContentAnalyzerModule();
    this.planner = new PlannerModule();
    this.scriptGenerator = new ScriptGeneratorModule();
    this.tts = new TTSModule();
    this.subtitleGenerator = new SubtitleGeneratorModule();
    this.videoComposer = new VideoComposerModule();
    this.thumbnailGenerator = new ThumbnailGeneratorModule();
    this.qualityReview = new QualityReviewModule();
  }

  /**
   * 전체 파이프라인 실행
   */
  async execute(input: ContentIntakeInput): Promise<OutputPackage> {
    const startTime = Date.now();
    const jobId = uuidv4();

    const jobContext: JobContext = {
      jobId,
      status: JobStatus.IN_PROGRESS,
      createdAt: new Date(),
      updatedAt: new Date(),
      outputPath: path.join(this.config.outputDir!, jobId),
      metadata: {},
    };

    try {
      console.log(`\n========================================`);
      console.log(`🚀 작업 시작: ${jobId}`);
      console.log(`========================================\n`);

      // 출력 디렉토리 생성
      await fs.mkdir(jobContext.outputPath, { recursive: true });
      await fs.mkdir(path.join(jobContext.outputPath, 'temp'), { recursive: true });

      // 1. 콘텐츠 인입
      console.log('📥 [1/9] 콘텐츠 인입 중...');
      const intakeResult = await this.contentIntake.execute(input);
      if (!intakeResult.success || !intakeResult.data) {
        throw new Error('콘텐츠 인입 실패');
      }
      console.log(`✅ 콘텐츠 인입 완료 (${intakeResult.data.cleanedText.length}자)\n`);

      // 2. 콘텐츠 분석
      console.log('🔍 [2/9] 콘텐츠 분석 중...');
      const analysisResult = await this.contentAnalyzer.execute({
        text: intakeResult.data.cleanedText,
        metadata: intakeResult.data.metadata,
      });
      if (!analysisResult.success || !analysisResult.data) {
        throw new Error('콘텐츠 분석 실패');
      }
      console.log(`✅ 콘텐츠 분석 완료 (타입: ${analysisResult.data.contentType}, 톤: ${analysisResult.data.tone})\n`);

      // 3. 플래닝
      console.log('📋 [3/9] 영상 계획 수립 중...');
      const planResult = await this.planner.execute({
        contentAnalysis: analysisResult.data,
        originalText: intakeResult.data.cleanedText,
        targetLength: this.config.targetVideoLength,
      });
      if (!planResult.success || !planResult.data) {
        throw new Error('플래닝 실패');
      }
      console.log(`✅ 영상 계획 완료 (목표 길이: ${planResult.data.targetDuration}초)\n`);

      // 4. 스크립트 생성
      console.log('✍️  [4/9] 스크립트 생성 중...');
      const scriptResult = await this.scriptGenerator.execute({
        originalText: intakeResult.data.cleanedText,
        plan: planResult.data,
        contentAnalysis: analysisResult.data,
      });
      if (!scriptResult.success || !scriptResult.data) {
        throw new Error('스크립트 생성 실패');
      }
      console.log(`✅ 스크립트 생성 완료 (섹션: ${scriptResult.data.sections.length}개, 단어: ${scriptResult.data.metadata.wordCount}개)\n`);

      // 5. 품질 검토 (옵션)
      if (this.config.qualityCheckEnabled) {
        console.log('🔎 [5/9] 품질 검토 중...');
        const reviewResult = await this.qualityReview.execute({
          originalText: intakeResult.data.cleanedText,
          generatedScript: scriptResult.data,
          contentAnalysis: analysisResult.data,
        });

        if (!reviewResult.success || !reviewResult.data) {
          throw new Error('품질 검토 실패');
        }

        console.log(`✅ 품질 검토 완료 (점수: ${reviewResult.data.score}/100, 권장: ${reviewResult.data.recommendation})\n`);

        if (reviewResult.data.recommendation === 'reject') {
          throw new Error(
            `품질 검토 실패: 점수가 너무 낮습니다 (${reviewResult.data.score}/100)`
          );
        }

        if (reviewResult.data.issues.length > 0) {
          console.log('⚠️  발견된 문제:');
          reviewResult.data.issues.forEach((issue) => {
            console.log(`  - [${issue.severity}] ${issue.description}`);
          });
          console.log();
        }
      } else {
        console.log('⏭️  [5/9] 품질 검토 건너뛰기\n');
      }

      // 6. TTS (음성 합성)
      console.log('🎤 [6/9] 음성 합성 중...');
      const ttsResult = await this.tts.execute({
        script: scriptResult.data,
      });
      if (!ttsResult.success || !ttsResult.data) {
        throw new Error('TTS 변환 실패');
      }
      console.log(`✅ 음성 합성 완료 (총 길이: ${ttsResult.data.totalDuration.toFixed(2)}초)\n`);

      // 7. 자막 생성
      console.log('💬 [7/9] 자막 생성 중...');
      const subtitleResult = await this.subtitleGenerator.execute({
        scriptWithTimestamps: ttsResult.data.scriptWithTimestamps,
        format: 'srt',
      });
      if (!subtitleResult.success || !subtitleResult.data) {
        throw new Error('자막 생성 실패');
      }
      console.log(`✅ 자막 생성 완료 (${subtitleResult.data.entries.length}개 항목)\n`);

      // 8. 영상 합성
      console.log('🎬 [8/9] 영상 합성 중...');
      const videoResult = await this.videoComposer.execute({
        audioPath: ttsResult.data.masterAudioPath,
        totalDuration: ttsResult.data.totalDuration,
        subtitlePath: subtitleResult.data.subtitlePath,
        scriptWithTimestamps: ttsResult.data.scriptWithTimestamps,
        options: {
          burnSubtitles: true,
          resolution: '1920x1080',
          fps: 30,
        },
      });
      if (!videoResult.success || !videoResult.data) {
        throw new Error('영상 합성 실패');
      }
      console.log(`✅ 영상 합성 완료 (크기: ${(videoResult.data.fileSize / 1024 / 1024).toFixed(2)}MB)\n`);

      // 9. 썸네일 생성
      console.log('🖼️  [9/9] 썸네일 생성 중...');
      const thumbnailResult = await this.thumbnailGenerator.execute({
        title: intakeResult.data.metadata.title || '제목 없음',
        keywords: analysisResult.data.keywords,
        contentType: analysisResult.data.contentType,
      });
      if (!thumbnailResult.success || !thumbnailResult.data) {
        throw new Error('썸네일 생성 실패');
      }
      console.log(`✅ 썸네일 생성 완료\n`);

      // 최종 파일 패키징
      console.log('📦 최종 패키지 생성 중...');
      const outputPackage = await this.packageOutputs(
        jobContext,
        {
          intake: intakeResult.data,
          analysis: analysisResult.data,
          script: ttsResult.data.scriptWithTimestamps,
          video: videoResult.data,
          subtitle: subtitleResult.data,
          thumbnail: thumbnailResult.data,
          audio: ttsResult.data,
        },
        startTime
      );

      jobContext.status = JobStatus.COMPLETED;
      jobContext.updatedAt = new Date();

      console.log(`\n========================================`);
      console.log(`✨ 작업 완료!`);
      console.log(`========================================`);
      console.log(`📂 출력 위치: ${jobContext.outputPath}`);
      console.log(`⏱️  처리 시간: ${((Date.now() - startTime) / 1000).toFixed(2)}초`);
      console.log(`🎥 영상 길이: ${outputPackage.metadata.duration.toFixed(2)}초`);
      console.log(`========================================\n`);

      return outputPackage;
    } catch (error) {
      jobContext.status = JobStatus.FAILED;
      jobContext.updatedAt = new Date();

      console.error(`\n❌ 작업 실패: ${error instanceof Error ? error.message : '알 수 없는 오류'}`);

      if (error instanceof ModuleError) {
        console.error(`모듈: ${error.moduleType}`);
        if (error.originalError) {
          console.error(`원인: ${error.originalError.message}`);
        }
      }

      throw error;
    }
  }

  /**
   * 최종 산출물 패키징
   */
  private async packageOutputs(
    jobContext: JobContext,
    results: any,
    startTime: number
  ): Promise<OutputPackage> {
    const finalDir = jobContext.outputPath;

    // 파일 복사 및 정리
    const finalVideoPaths = {
      video: path.join(finalDir, 'final_video.mp4'),
      videoClean: results.video.videoPathClean
        ? path.join(finalDir, 'final_video_clean.mp4')
        : undefined,
      subtitles: path.join(finalDir, 'video_subtitles.srt'),
      audio: path.join(finalDir, 'audio_master.wav'),
      script: path.join(finalDir, 'script.json'),
      thumbnail: path.join(finalDir, 'thumbnail_base.png'),
      metadata: path.join(finalDir, 'metadata.json'),
    };

    // 파일 복사
    await fs.copyFile(results.video.videoPath, finalVideoPaths.video);
    if (results.video.videoPathClean && finalVideoPaths.videoClean) {
      await fs.copyFile(results.video.videoPathClean, finalVideoPaths.videoClean);
    }
    await fs.copyFile(results.subtitle.subtitlePath, finalVideoPaths.subtitles);
    await fs.copyFile(results.audio.masterAudioPath, finalVideoPaths.audio);
    await fs.copyFile(results.thumbnail.thumbnailPath, finalVideoPaths.thumbnail);

    // 스크립트 저장
    await fs.writeFile(finalVideoPaths.script, JSON.stringify(results.script, null, 2), 'utf-8');

    // 메타데이터 생성
    const metadata = {
      jobId: jobContext.jobId,
      originalSource: results.intake.originalSource,
      title: results.intake.metadata.title || '제목 없음',
      author: results.intake.metadata.author,
      publishedDate: results.intake.metadata.publishedDate,
      contentType: results.analysis.contentType,
      tone: results.analysis.tone,
      keywords: results.analysis.keywords,
      duration: results.video.duration,
      resolution: results.video.resolution,
      fileSize: results.video.fileSize,
      createdAt: jobContext.createdAt,
      processingTime: (Date.now() - startTime) / 1000,
    };

    await fs.writeFile(finalVideoPaths.metadata, JSON.stringify(metadata, null, 2), 'utf-8');

    const outputPackage: OutputPackage = {
      jobId: jobContext.jobId,
      paths: finalVideoPaths as any,
      metadata: {
        originalSource: results.intake.originalSource,
        title: results.intake.metadata.title,
        duration: results.video.duration,
        createdAt: jobContext.createdAt,
        processingTime: (Date.now() - startTime) / 1000,
      },
    };

    return outputPackage;
  }
}
