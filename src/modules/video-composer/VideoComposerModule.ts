/**
 * 영상 합성 모듈
 * 오디오, 비주얼, 자막을 합쳐서 최종 영상 생성
 */

import * as fs from 'fs/promises';
import * as path from 'path';
import {
  IVideoComposerModule,
  VideoComposerInput,
  VideoComposerOutput,
  ModuleResult,
  ModuleType,
  ModuleError,
} from '@/types';

export class VideoComposerModule implements IVideoComposerModule {
  getName(): string {
    return 'VideoComposerModule';
  }

  async execute(input: VideoComposerInput): Promise<ModuleResult<VideoComposerOutput>> {
    try {
      await this.validate(input);

      const result = await this.composeVideo(input);

      return {
        success: true,
        data: result,
        timestamp: new Date(),
        moduleType: ModuleType.VIDEO_COMPOSER,
      };
    } catch (error) {
      throw new ModuleError(
        ModuleType.VIDEO_COMPOSER,
        `영상 합성 실패: ${error instanceof Error ? error.message : '알 수 없는 오류'}`,
        error instanceof Error ? error : undefined
      );
    }
  }

  async validate(input: VideoComposerInput): Promise<boolean> {
    if (!input.audioPath) {
      throw new Error('오디오 파일 경로가 없습니다.');
    }

    // 오디오 파일 존재 확인
    try {
      await fs.access(input.audioPath);
    } catch {
      throw new Error(`오디오 파일을 찾을 수 없습니다: ${input.audioPath}`);
    }

    if (input.totalDuration <= 0) {
      throw new Error('영상 길이가 유효하지 않습니다.');
    }

    return true;
  }

  async composeVideo(input: VideoComposerInput): Promise<VideoComposerOutput> {
    // TODO: FFmpeg를 사용하여 실제 영상 합성
    // 현재는 더미 구현

    console.log('[VideoComposer] 영상 합성 시작...');

    const resolution = input.options?.resolution || '1920x1080';
    const fps = input.options?.fps || 30;
    const burnSubtitles = input.options?.burnSubtitles ?? true;

    const videoPath = path.join(process.cwd(), 'outputs', 'temp', `video_${Date.now()}.mp4`);

    await fs.mkdir(path.dirname(videoPath), { recursive: true });

    // 1. 배경 비디오 생성 (정적 이미지 또는 슬라이드쇼)
    console.log('[VideoComposer] 배경 비디오 생성 중...');
    const backgroundVideoPath = await this.createBackgroundVideo(input);

    // 2. 오디오 추가
    console.log('[VideoComposer] 오디오 추가 중...');
    const videoWithAudioPath = await this.addAudioToVideo(backgroundVideoPath, input.audioPath);

    // 3. 자막 번인 (옵션)
    let finalVideoPath = videoWithAudioPath;
    if (burnSubtitles && input.subtitlePath) {
      console.log('[VideoComposer] 자막 번인 중...');
      finalVideoPath = await this.burnSubtitles(videoWithAudioPath, input.subtitlePath);
    }

    // 더미 파일 생성
    await fs.writeFile(finalVideoPath, Buffer.from('...MP4...'), 'binary');

    // 파일 크기 가져오기
    const stats = await fs.stat(finalVideoPath);

    const result: VideoComposerOutput = {
      videoPath: finalVideoPath,
      resolution,
      duration: input.totalDuration,
      fileSize: stats.size,
    };

    // 자막 없는 버전 생성 (옵션)
    if (burnSubtitles && input.subtitlePath) {
      result.videoPathClean = videoWithAudioPath;
    }

    console.log('[VideoComposer] 영상 합성 완료!');

    return result;
  }

  async burnSubtitles(videoPath: string, subtitlePath: string): Promise<string> {
    // TODO: FFmpeg로 자막 번인
    // ffmpeg -i video.mp4 -vf subtitles=subtitle.srt output.mp4

    console.log('[VideoComposer] 자막 번인 중...');

    const outputPath = videoPath.replace('.mp4', '_with_subs.mp4');
    await fs.copyFile(videoPath, outputPath);

    return outputPath;
  }

  async addAudioToVideo(videoPath: string, audioPath: string): Promise<string> {
    // TODO: FFmpeg로 오디오 추가
    // ffmpeg -i video.mp4 -i audio.wav -c:v copy -c:a aac output.mp4

    console.log('[VideoComposer] 오디오 추가 중...');

    const outputPath = videoPath.replace('.mp4', '_with_audio.mp4');
    await fs.copyFile(videoPath, outputPath);

    return outputPath;
  }

  private async createBackgroundVideo(input: VideoComposerInput): Promise<string> {
    // TODO: FFmpeg로 배경 비디오 생성
    // 1. 단색 배경
    // 2. 이미지 슬라이드쇼
    // 3. 키워드 기반 시각적 큐

    console.log('[VideoComposer] 배경 비디오 생성 중...');

    const outputPath = path.join(
      process.cwd(),
      'outputs',
      'temp',
      `background_${Date.now()}.mp4`
    );

    await fs.mkdir(path.dirname(outputPath), { recursive: true });
    await fs.writeFile(outputPath, Buffer.from('...MP4...'), 'binary');

    return outputPath;
  }
}
