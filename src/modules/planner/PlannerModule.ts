/**
 * LLM 플래너 모듈
 * 콘텐츠 분석 결과를 토대로 영상 구조 기획
 */

import {
  IPlannerModule,
  PlannerInput,
  PlannerOutput,
  ModuleResult,
  ModuleType,
  ModuleError,
  ContentTone,
} from '@/types';

export class PlannerModule implements IPlannerModule {
  getName(): string {
    return 'PlannerModule';
  }

  async execute(input: PlannerInput): Promise<ModuleResult<PlannerOutput>> {
    try {
      await this.validate(input);

      const plan = await this.createVideoPlan(input);
      const optimizedPlan = await this.optimizePlan(plan);

      return {
        success: true,
        data: optimizedPlan,
        timestamp: new Date(),
        moduleType: ModuleType.PLANNER,
      };
    } catch (error) {
      throw new ModuleError(
        ModuleType.PLANNER,
        `플래닝 실패: ${error instanceof Error ? error.message : '알 수 없는 오류'}`,
        error instanceof Error ? error : undefined
      );
    }
  }

  async validate(input: PlannerInput): Promise<boolean> {
    if (!input.contentAnalysis) {
      throw new Error('콘텐츠 분석 결과가 없습니다.');
    }
    if (!input.originalText || input.originalText.trim().length === 0) {
      throw new Error('원본 텍스트가 비어있습니다.');
    }
    return true;
  }

  async createVideoPlan(input: PlannerInput): Promise<PlannerOutput> {
    // TODO: LLM을 사용하여 영상 구조 기획
    // 현재는 기본 구조 반환

    const targetDuration = input.targetLength || input.contentAnalysis.estimatedReadingTime * 60;

    const plan: PlannerOutput = {
      targetDuration,
      structure: [
        {
          sectionType: 'hook',
          estimatedDuration: Math.min(15, targetDuration * 0.1),
          objectives: ['시청자의 관심 유도', '핵심 메시지 예고'],
        },
        {
          sectionType: 'introduction',
          estimatedDuration: targetDuration * 0.15,
          objectives: ['주제 소개', '배경 설명'],
        },
        {
          sectionType: 'main_content',
          estimatedDuration: targetDuration * 0.6,
          objectives: ['핵심 내용 전달', '상세 설명'],
        },
        {
          sectionType: 'summary',
          estimatedDuration: targetDuration * 0.1,
          objectives: ['핵심 요약'],
        },
        {
          sectionType: 'conclusion',
          estimatedDuration: targetDuration * 0.05,
          objectives: ['마무리', '메시지 강조'],
        },
      ],
      tone: input.contentAnalysis.tone,
      pacing: 'medium',
      visualStyle: 'slideshow',
    };

    return plan;
  }

  async optimizePlan(plan: PlannerOutput): Promise<PlannerOutput> {
    // TODO: 계획 최적화 로직
    return plan;
  }
}
