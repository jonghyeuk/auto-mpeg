/**
 * 메인 엔트리 포인트
 */

import dotenv from 'dotenv';
import { VideoOrchestrator } from './orchestrator';
import { ContentIntakeInput } from './types';
import { defaultConfig } from './config';
import logger from './utils/logger';

// 환경 변수 로드
dotenv.config();

/**
 * CLI 실행 예제
 */
async function main() {
  try {
    // 명령줄 인자 파싱
    const args = process.argv.slice(2);

    if (args.length === 0) {
      console.log(`
사용법:
  npm run dev <URL 또는 텍스트> [옵션]

옵션:
  --type <url|text>           입력 타입 (기본값: url)
  --target-length <초>        목표 영상 길이 (선택)
  --no-quality-check          품질 검토 건너뛰기

예제:
  npm run dev "https://blog.example.com/post" --type url
  npm run dev "블로그 내용..." --type text
      `);
      process.exit(0);
    }

    const source = args[0];
    const typeIndex = args.indexOf('--type');
    const sourceType = typeIndex !== -1 ? args[typeIndex + 1] : 'url';

    const targetLengthIndex = args.indexOf('--target-length');
    const targetLength =
      targetLengthIndex !== -1 ? parseInt(args[targetLengthIndex + 1], 10) : undefined;

    const qualityCheckEnabled = !args.includes('--no-quality-check');

    // 입력 준비
    const input: ContentIntakeInput = {
      source,
      sourceType: sourceType as 'url' | 'text',
    };

    // 오케스트레이터 생성
    const orchestrator = new VideoOrchestrator({
      outputDir: defaultConfig.output.baseDir,
      qualityCheckEnabled,
      targetVideoLength: targetLength,
    });

    // 실행
    const result = await orchestrator.execute(input);

    console.log('\n🎉 완료!');
    console.log(`📂 출력 디렉토리: ${result.paths.video}`);
  } catch (error) {
    console.error('\n❌ 오류 발생:', error instanceof Error ? error.message : error);
    logger.error('실행 오류', { error });
    process.exit(1);
  }
}

// CLI로 실행된 경우
if (require.main === module) {
  main();
}

// 라이브러리로 사용 시 export
export { VideoOrchestrator } from './orchestrator';
export * from './types';
export { defaultConfig } from './config';
