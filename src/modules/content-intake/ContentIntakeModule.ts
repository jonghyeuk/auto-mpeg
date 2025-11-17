/**
 * 콘텐츠 인입 모듈
 * 블로그 URL 또는 텍스트를 입력받아 깨끗한 텍스트로 정제
 */

import axios from 'axios';
import * as cheerio from 'cheerio';
import {
  IContentIntakeModule,
  ContentIntakeInput,
  ContentIntakeOutput,
  ModuleResult,
  ModuleType,
  ModuleError,
} from '@/types';

export class ContentIntakeModule implements IContentIntakeModule {
  getName(): string {
    return 'ContentIntakeModule';
  }

  async execute(input: ContentIntakeInput): Promise<ModuleResult<ContentIntakeOutput>> {
    try {
      await this.validate(input);

      let result: ContentIntakeOutput;

      if (input.sourceType === 'url') {
        result = await this.extractFromUrl(input.source);
      } else {
        const cleanedText = await this.cleanText(input.source);
        result = {
          cleanedText,
          originalSource: input.source,
          sourceType: 'text',
          metadata: {
            extractedAt: new Date(),
          },
        };
      }

      return {
        success: true,
        data: result,
        timestamp: new Date(),
        moduleType: ModuleType.CONTENT_INTAKE,
      };
    } catch (error) {
      throw new ModuleError(
        ModuleType.CONTENT_INTAKE,
        `콘텐츠 인입 실패: ${error instanceof Error ? error.message : '알 수 없는 오류'}`,
        error instanceof Error ? error : undefined
      );
    }
  }

  async validate(input: ContentIntakeInput): Promise<boolean> {
    if (!input.source || input.source.trim().length === 0) {
      throw new Error('입력 소스가 비어있습니다.');
    }

    if (input.sourceType === 'url') {
      try {
        new URL(input.source);
      } catch {
        throw new Error('유효하지 않은 URL입니다.');
      }
    }

    return true;
  }

  async extractFromUrl(url: string): Promise<ContentIntakeOutput> {
    try {
      const response = await axios.get(url, {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        },
        timeout: 30000,
      });

      const $ = cheerio.load(response.data);

      // 불필요한 요소 제거
      $('script, style, nav, footer, aside, .advertisement, .comment').remove();

      // 메타데이터 추출
      const title = $('title').text() || $('h1').first().text() || '';
      const author = $('meta[name="author"]').attr('content') || '';
      const publishedDate = $('meta[property="article:published_time"]').attr('content') || '';

      // 본문 추출 (일반적인 블로그 구조에서)
      let mainContent = '';
      const possibleSelectors = [
        'article',
        '.post-content',
        '.entry-content',
        '.content',
        'main',
        '.article-body',
      ];

      for (const selector of possibleSelectors) {
        const content = $(selector).text();
        if (content && content.length > mainContent.length) {
          mainContent = content;
        }
      }

      // 선택자로 찾지 못한 경우 body 전체 사용
      if (!mainContent) {
        mainContent = $('body').text();
      }

      const cleanedText = await this.cleanText(mainContent);

      return {
        cleanedText,
        originalSource: url,
        sourceType: 'url',
        metadata: {
          title: title.trim(),
          author: author.trim(),
          publishedDate: publishedDate.trim(),
          extractedAt: new Date(),
        },
      };
    } catch (error) {
      throw new Error(
        `URL에서 콘텐츠 추출 실패: ${error instanceof Error ? error.message : '알 수 없는 오류'}`
      );
    }
  }

  async cleanText(text: string): Promise<string> {
    let cleaned = text;

    // HTML 엔티티 디코딩
    cleaned = cleaned
      .replace(/&nbsp;/g, ' ')
      .replace(/&amp;/g, '&')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'");

    // 연속된 공백을 하나로
    cleaned = cleaned.replace(/\s+/g, ' ');

    // 연속된 줄바꿈을 최대 2개로
    cleaned = cleaned.replace(/\n{3,}/g, '\n\n');

    // 앞뒤 공백 제거
    cleaned = cleaned.trim();

    return cleaned;
  }
}
