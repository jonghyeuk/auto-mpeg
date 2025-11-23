#!/bin/bash
# 캐시 정리 스크립트

echo "🗑️  Auto-MPEG 캐시 정리"
echo "======================="
echo ""
echo "선택하세요:"
echo "1) 전체 삭제 (임시 파일 + 메타데이터 + 최종 영상)"
echo "2) 임시 파일만 삭제 (최종 영상 보존)"
echo "3) 최종 영상만 삭제 (작업 데이터 보존)"
echo "4) 취소"
echo ""
read -p "선택 (1-4): " choice

case $choice in
  1)
    echo "🗑️  전체 삭제 중..."
    rm -rf data/temp data/meta data/output
    echo "✅ 완료!"
    ;;
  2)
    echo "🗑️  임시 파일 삭제 중..."
    rm -rf data/temp data/meta
    echo "✅ 완료! (최종 영상 보존됨)"
    ;;
  3)
    echo "🗑️  최종 영상 삭제 중..."
    rm -rf data/output
    echo "✅ 완료! (작업 데이터 보존됨)"
    ;;
  4)
    echo "❌ 취소됨"
    ;;
  *)
    echo "❌ 잘못된 선택"
    ;;
esac
