/**
 * 자막 생성기 모듈
 * 타임스탬프가 포함된 스크립트로 자막 파일 생성
 */

import * as fs from 'fs/promises';
import * as path from 'path';
import {
  ISubtitleGeneratorModule,
  SubtitleGeneratorInput,
  SubtitleGeneratorOutput,
  ModuleResult,
  ModuleType,
  ModuleError,
  SubtitleEntry,
} from '@/types';

export class SubtitleGeneratorModule implements ISubtitleGeneratorModule {
  getName(): string {
    return 'SubtitleGeneratorModule';
  }

  async execute(input: SubtitleGeneratorInput): Promise<ModuleResult<SubtitleGeneratorOutput>> {
    try {
      await this.validate(input);

      const format = input.format || 'srt';
      let subtitleContent: string;

      if (format === 'srt') {
        subtitleContent = await this.generateSRT(input);
      } else if (format === 'vtt') {
        subtitleContent = await this.generateVTT(input);
      } else {
        throw new Error(`지원하지 않는 자막 형식: ${format}`);
      }

      const subtitlePath = path.join(
        process.cwd(),
        'outputs',
        'temp',
        `subtitles_${Date.now()}.${format}`
      );

      await fs.mkdir(path.dirname(subtitlePath), { recursive: true });
      await fs.writeFile(subtitlePath, subtitleContent, 'utf-8');

      const entries = this.parseSubtitleEntries(input);

      const result: SubtitleGeneratorOutput = {
        subtitlePath,
        format,
        entries,
      };

      return {
        success: true,
        data: result,
        timestamp: new Date(),
        moduleType: ModuleType.SUBTITLE_GENERATOR,
      };
    } catch (error) {
      throw new ModuleError(
        ModuleType.SUBTITLE_GENERATOR,
        `자막 생성 실패: ${error instanceof Error ? error.message : '알 수 없는 오류'}`,
        error instanceof Error ? error : undefined
      );
    }
  }

  async validate(input: SubtitleGeneratorInput): Promise<boolean> {
    if (!input.scriptWithTimestamps) {
      throw new Error('타임스탬프가 포함된 스크립트가 없습니다.');
    }

    // 타임스탬프 검증
    for (const section of input.scriptWithTimestamps.sections) {
      for (const line of section.lines) {
        if (line.startTime === undefined || line.endTime === undefined) {
          throw new Error(`라인 ${line.id}에 타임스탬프가 없습니다.`);
        }
      }
    }

    return true;
  }

  async generateSRT(input: SubtitleGeneratorInput): Promise<string> {
    const lines: string[] = [];
    let index = 1;

    for (const section of input.scriptWithTimestamps.sections) {
      for (const line of section.lines) {
        if (line.startTime === undefined || line.endTime === undefined) {
          continue;
        }

        lines.push(index.toString());
        lines.push(
          `${this.formatSRTTime(line.startTime)} --> ${this.formatSRTTime(line.endTime)}`
        );
        lines.push(line.text);
        lines.push(''); // 빈 줄

        index++;
      }
    }

    return lines.join('\n');
  }

  async generateVTT(input: SubtitleGeneratorInput): Promise<string> {
    const srtContent = await this.generateSRT(input);
    return 'WEBVTT\n\n' + srtContent.replace(/,/g, '.');
  }

  private formatSRTTime(seconds: number): string {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    const millis = Math.floor((seconds % 1) * 1000);

    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')},${String(millis).padStart(3, '0')}`;
  }

  private parseSubtitleEntries(input: SubtitleGeneratorInput): SubtitleEntry[] {
    const entries: SubtitleEntry[] = [];
    let index = 1;

    for (const section of input.scriptWithTimestamps.sections) {
      for (const line of section.lines) {
        if (line.startTime === undefined || line.endTime === undefined) {
          continue;
        }

        entries.push({
          index,
          startTime: this.formatSRTTime(line.startTime),
          endTime: this.formatSRTTime(line.endTime),
          text: line.text,
        });

        index++;
      }
    }

    return entries;
  }
}
