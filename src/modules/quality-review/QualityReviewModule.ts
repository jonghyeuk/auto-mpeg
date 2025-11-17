/**
 * 품질 검토 모듈
 * LLM을 사용하여 생성된 스크립트의 품질 검증
 */

import {
  IQualityReviewModule,
  QualityReviewInput,
  QualityReviewOutput,
  ModuleResult,
  ModuleType,
  ModuleError,
  QualityIssue,
} from '@/types';

export class QualityReviewModule implements IQualityReviewModule {
  getName(): string {
    return 'QualityReviewModule';
  }

  async execute(input: QualityReviewInput): Promise<ModuleResult<QualityReviewOutput>> {
    try {
      await this.validate(input);

      const result = await this.reviewScript(input);

      return {
        success: true,
        data: result,
        timestamp: new Date(),
        moduleType: ModuleType.QUALITY_REVIEW,
      };
    } catch (error) {
      throw new ModuleError(
        ModuleType.QUALITY_REVIEW,
        `품질 검토 실패: ${error instanceof Error ? error.message : '알 수 없는 오류'}`,
        error instanceof Error ? error : undefined
      );
    }
  }

  async validate(input: QualityReviewInput): Promise<boolean> {
    if (!input.originalText || input.originalText.trim().length === 0) {
      throw new Error('원본 텍스트가 비어있습니다.');
    }
    if (!input.generatedScript) {
      throw new Error('생성된 스크립트가 없습니다.');
    }
    return true;
  }

  async reviewScript(input: QualityReviewInput): Promise<QualityReviewOutput> {
    // TODO: LLM을 사용하여 실제 품질 검토
    // 1. 사실관계 확인
    // 2. 톤앤매너 일치 여부
    // 3. 중요 정보 누락 여부
    // 4. 과장/왜곡 여부

    console.log('[QualityReview] 품질 검토 시작...');

    const issues: QualityIssue[] = [];

    // 간단한 검증: 사실 확인
    const isFactuallyAccurate = await this.checkFactualAccuracy(
      input.originalText,
      this.extractScriptText(input.generatedScript)
    );

    if (!isFactuallyAccurate) {
      issues.push({
        severity: 'high',
        category: 'factual_error',
        description: '원본과 생성된 스크립트 간의 사실 관계 불일치 가능성이 있습니다.',
        suggestion: '스크립트를 재검토하고 필요시 수정하세요.',
      });
    }

    // 점수 계산
    const score = this.calculateQualityScore(issues);

    // 권장사항 결정
    let recommendation: 'approve' | 'revise' | 'reject';
    if (score >= 80) {
      recommendation = 'approve';
    } else if (score >= 60) {
      recommendation = 'revise';
    } else {
      recommendation = 'reject';
    }

    console.log(`[QualityReview] 품질 점수: ${score}/100`);
    console.log(`[QualityReview] 권장사항: ${recommendation}`);

    return {
      passed: score >= 70,
      score,
      issues,
      recommendation,
      reviewedAt: new Date(),
    };
  }

  async checkFactualAccuracy(original: string, generated: string): Promise<boolean> {
    // TODO: LLM을 사용하여 사실관계 확인
    // 현재는 간단한 키워드 비교
    const originalWords = new Set(original.toLowerCase().split(/\s+/));
    const generatedWords = new Set(generated.toLowerCase().split(/\s+/));

    // 원본의 주요 단어가 생성된 스크립트에 포함되어 있는지 확인
    let matchCount = 0;
    let totalImportantWords = 0;

    for (const word of originalWords) {
      if (word.length > 3) {
        totalImportantWords++;
        if (generatedWords.has(word)) {
          matchCount++;
        }
      }
    }

    const matchRate = totalImportantWords > 0 ? matchCount / totalImportantWords : 0;
    return matchRate > 0.5; // 50% 이상 일치하면 사실관계 일치로 간주
  }

  private extractScriptText(script: any): string {
    let text = '';
    for (const section of script.sections) {
      for (const line of section.lines) {
        text += line.text + ' ';
      }
    }
    return text;
  }

  private calculateQualityScore(issues: QualityIssue[]): number {
    let score = 100;

    for (const issue of issues) {
      switch (issue.severity) {
        case 'critical':
          score -= 30;
          break;
        case 'high':
          score -= 20;
          break;
        case 'medium':
          score -= 10;
          break;
        case 'low':
          score -= 5;
          break;
      }
    }

    return Math.max(0, score);
  }
}
