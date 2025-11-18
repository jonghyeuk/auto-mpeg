/**
 * HighlightBox 컴포넌트
 * 슬라이드의 특정 영역을 박스로 강조
 */
import React from 'react';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';

interface HighlightBoxProps {
  x: number;
  y: number;
  width: number;
  height: number;
  start: number;  // 시작 시간 (초)
  end: number;    // 종료 시간 (초)
  text?: string;
  color?: string;
}

export const HighlightBox: React.FC<HighlightBoxProps> = ({
  x,
  y,
  width,
  height,
  start,
  end,
  text,
  color = 'yellow',
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // 초를 프레임으로 변환
  const startFrame = start * fps;
  const endFrame = end * fps;

  // 현재 프레임이 범위 밖이면 렌더링하지 않음
  if (frame < startFrame || frame > endFrame) {
    return null;
  }

  // 페이드 인/아웃 애니메이션
  const progress = (frame - startFrame) / (endFrame - startFrame);
  const opacity = interpolate(
    progress,
    [0, 0.1, 0.9, 1],
    [0, 1, 1, 0],
    {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    }
  );

  // 스케일 애니메이션
  const scale = spring({
    frame: frame - startFrame,
    fps,
    config: {
      damping: 200,
      stiffness: 100,
    },
  });

  return (
    <div
      style={{
        position: 'absolute',
        left: x,
        top: y,
        width,
        height,
        border: `4px solid ${color}`,
        borderRadius: '8px',
        boxShadow: `0 0 20px ${color}`,
        opacity,
        transform: `scale(${scale})`,
        pointerEvents: 'none',
      }}
    >
      {text && (
        <div
          style={{
            position: 'absolute',
            top: -40,
            left: 0,
            background: color,
            color: 'black',
            padding: '8px 16px',
            borderRadius: '4px',
            fontSize: '24px',
            fontWeight: 'bold',
            whiteSpace: 'nowrap',
          }}
        >
          {text}
        </div>
      )}
    </div>
  );
};
