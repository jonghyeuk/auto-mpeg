/**
 * 콘텐츠 분석기 모듈
 * 텍스트를 분석하여 영상화를 위한 기초 데이터 생성
 */

import {
  IContentAnalyzerModule,
  ContentAnalyzerInput,
  ContentAnalyzerOutput,
  ModuleResult,
  ModuleType,
  ModuleError,
  ContentType,
  ContentTone,
} from '@/types';

export class ContentAnalyzerModule implements IContentAnalyzerModule {
  getName(): string {
    return 'ContentAnalyzerModule';
  }

  async execute(input: ContentAnalyzerInput): Promise<ModuleResult<ContentAnalyzerOutput>> {
    try {
      await this.validate(input);

      const structure = await this.analyzeStructure(input.text);
      const keywords = await this.extractKeywords(input.text);
      const tone = await this.detectTone(input.text);
      const contentType = await this.detectContentType(input.text);
      const coreMessage = await this.extractCoreMessage(input.text);
      const estimatedReadingTime = this.calculateReadingTime(input.text);
      const complexity = this.assessComplexity(input.text);

      const result: ContentAnalyzerOutput = {
        contentType,
        tone,
        structure,
        keywords,
        coreMessage,
        estimatedReadingTime,
        complexity,
      };

      return {
        success: true,
        data: result,
        timestamp: new Date(),
        moduleType: ModuleType.CONTENT_ANALYZER,
      };
    } catch (error) {
      throw new ModuleError(
        ModuleType.CONTENT_ANALYZER,
        `콘텐츠 분석 실패: ${error instanceof Error ? error.message : '알 수 없는 오류'}`,
        error instanceof Error ? error : undefined
      );
    }
  }

  async validate(input: ContentAnalyzerInput): Promise<boolean> {
    if (!input.text || input.text.trim().length === 0) {
      throw new Error('분석할 텍스트가 비어있습니다.');
    }

    if (input.text.length < 100) {
      throw new Error('텍스트가 너무 짧습니다. 최소 100자 이상이어야 합니다.');
    }

    return true;
  }

  async analyzeStructure(text: string): Promise<ContentAnalyzerOutput['structure']> {
    // TODO: LLM을 사용하여 더 정교한 구조 분석 구현
    // 현재는 간단한 단락 분할만 수행

    const paragraphs = text.split(/\n\n+/).filter((p) => p.trim().length > 0);

    const sections = paragraphs.map((content, index) => {
      const startIndex = text.indexOf(content);
      return {
        content: content.trim(),
        startIndex,
        endIndex: startIndex + content.length,
      };
    });

    return { sections };
  }

  async extractKeywords(text: string): Promise<string[]> {
    // TODO: LLM 또는 NLP 라이브러리를 사용하여 키워드 추출
    // 현재는 간단한 단어 빈도 분석

    const words = text
      .toLowerCase()
      .replace(/[^\w\s가-힣]/g, ' ')
      .split(/\s+/)
      .filter((word) => word.length > 2);

    const frequency: Record<string, number> = {};
    words.forEach((word) => {
      frequency[word] = (frequency[word] || 0) + 1;
    });

    const sortedWords = Object.entries(frequency)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10)
      .map(([word]) => word);

    return sortedWords;
  }

  async detectTone(text: string): Promise<ContentTone> {
    // TODO: LLM을 사용하여 톤 감지
    // 현재는 기본값 반환
    return ContentTone.NEUTRAL;
  }

  private async detectContentType(text: string): Promise<ContentType> {
    // TODO: LLM을 사용하여 콘텐츠 타입 분류
    // 현재는 기본값 반환
    return ContentType.INFORMATIONAL;
  }

  private async extractCoreMessage(text: string): Promise<string> {
    // TODO: LLM을 사용하여 핵심 메시지 추출
    // 현재는 첫 문장 반환
    const firstSentence = text.split(/[.!?]/).filter((s) => s.trim().length > 0)[0];
    return firstSentence?.trim() || '핵심 메시지를 추출할 수 없습니다.';
  }

  private calculateReadingTime(text: string): number {
    // 한국어: 분당 약 300자, 영어: 분당 약 200단어
    const koreanChars = (text.match(/[가-힣]/g) || []).length;
    const englishWords = (text.match(/[a-zA-Z]+/g) || []).length;

    const koreanTime = koreanChars / 300;
    const englishTime = englishWords / 200;

    return Math.ceil(koreanTime + englishTime);
  }

  private assessComplexity(text: string): 'simple' | 'moderate' | 'complex' {
    const avgSentenceLength =
      text.length / text.split(/[.!?]/).filter((s) => s.trim().length > 0).length;

    if (avgSentenceLength < 50) return 'simple';
    if (avgSentenceLength < 100) return 'moderate';
    return 'complex';
  }
}
