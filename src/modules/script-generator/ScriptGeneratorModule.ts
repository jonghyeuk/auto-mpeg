/**
 * 스크립트 생성기 모듈
 * 블로그 글을 영상용 구어체 대본으로 변환
 */

import { v4 as uuidv4 } from 'uuid';
import {
  IScriptGeneratorModule,
  ScriptGeneratorInput,
  ScriptGeneratorOutput,
  ModuleResult,
  ModuleType,
  ModuleError,
  ScriptSection,
  ScriptLine,
} from '@/types';

export class ScriptGeneratorModule implements IScriptGeneratorModule {
  getName(): string {
    return 'ScriptGeneratorModule';
  }

  async execute(input: ScriptGeneratorInput): Promise<ModuleResult<ScriptGeneratorOutput>> {
    try {
      await this.validate(input);

      const script = await this.generateScript(input);

      return {
        success: true,
        data: script,
        timestamp: new Date(),
        moduleType: ModuleType.SCRIPT_GENERATOR,
      };
    } catch (error) {
      throw new ModuleError(
        ModuleType.SCRIPT_GENERATOR,
        `스크립트 생성 실패: ${error instanceof Error ? error.message : '알 수 없는 오류'}`,
        error instanceof Error ? error : undefined
      );
    }
  }

  async validate(input: ScriptGeneratorInput): Promise<boolean> {
    if (!input.originalText || input.originalText.trim().length === 0) {
      throw new Error('원본 텍스트가 비어있습니다.');
    }
    if (!input.plan) {
      throw new Error('영상 계획이 없습니다.');
    }
    return true;
  }

  async generateScript(input: ScriptGeneratorInput): Promise<ScriptGeneratorOutput> {
    // TODO: LLM을 사용하여 구어체 대본 생성
    // 현재는 원문을 기반으로 간단한 섹션 분할만 수행

    const sections: ScriptSection[] = [];
    let totalWords = 0;
    let totalSentences = 0;

    for (let i = 0; i < input.plan.structure.length; i++) {
      const planSection = input.plan.structure[i];
      const sectionId = uuidv4();

      // 간단한 예시: 원문을 섹션별로 분할
      const sentences = this.extractSentencesForSection(input.originalText, i, input.plan.structure.length);

      const lines: ScriptLine[] = sentences.map((text, idx) => {
        const words = text.split(/\s+/).length;
        totalWords += words;
        totalSentences++;

        return {
          id: uuidv4(),
          sectionId,
          text,
          order: idx,
        };
      });

      sections.push({
        id: sectionId,
        type: planSection.sectionType,
        title: this.getSectionTitle(planSection.sectionType),
        lines,
        order: i,
      });
    }

    // 예상 발화 시간 계산 (분당 150단어 기준)
    const totalEstimatedDuration = (totalWords / 150) * 60;

    return {
      sections,
      totalEstimatedDuration,
      metadata: {
        wordCount: totalWords,
        sentenceCount: totalSentences,
        generatedAt: new Date(),
      },
    };
  }

  async refineSection(sectionId: string, feedback: string): Promise<ScriptGeneratorOutput> {
    // TODO: 특정 섹션 재생성
    throw new Error('Not implemented');
  }

  private extractSentencesForSection(text: string, sectionIndex: number, totalSections: number): string[] {
    const allSentences = text.split(/[.!?]/).filter((s) => s.trim().length > 0);
    const sentencesPerSection = Math.ceil(allSentences.length / totalSections);
    const start = sectionIndex * sentencesPerSection;
    const end = Math.min(start + sentencesPerSection, allSentences.length);

    return allSentences.slice(start, end).map((s) => s.trim() + '.');
  }

  private getSectionTitle(type: string): string {
    const titles: Record<string, string> = {
      hook: '오프닝',
      introduction: '도입',
      main_content: '본론',
      summary: '요약',
      conclusion: '결론',
      cta: '행동 유도',
    };
    return titles[type] || type;
  }
}
