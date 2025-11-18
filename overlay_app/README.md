# Overlay App (Remotion)

PPT 슬라이드에 강조 애니메이션 오버레이를 렌더링하는 Remotion 프로젝트

## 설치

```bash
cd overlay_app
npm install
```

## 사용 방법

### 1. 오버레이 렌더링

Python 백엔드에서 `overlay_plan.json`을 생성한 후, Remotion CLI를 사용하여 렌더링:

```bash
npx remotion render src/index.tsx SlideOverlay output/overlay_001.webm \
  --props='{"overlays": [...]}' \
  --codec=vp9 \
  --pixel-format=yuva420p
```

### 2. 알파 채널 지원

투명 배경을 위해 VP9 또는 ProRes 4444 코덱 사용:

```bash
# VP9 (WebM)
--codec=vp9 --pixel-format=yuva420p

# ProRes 4444 (MOV)
--codec=prores --prores-profile=4444
```

## 컴포넌트

### HighlightBox

특정 영역을 박스로 강조

```tsx
<HighlightBox
  x={200}
  y={150}
  width={300}
  height={120}
  start={1.0}
  end={5.0}
  text="강조할 내용"
  color="yellow"
/>
```

### FloatingText (TODO)

떠다니는 텍스트 레이블

### Arrow (TODO)

화살표로 특정 부분 지시

## 데이터 구조

`overlay_plan.json`:

```json
{
  "overlays": [
    {
      "type": "highlight_box",
      "x": 200,
      "y": 150,
      "width": 300,
      "height": 120,
      "start": 1.0,
      "end": 5.0,
      "text": "강조할 내용",
      "color": "yellow"
    }
  ]
}
```

## TODO (2단계)

- [ ] FloatingText 컴포넌트 구현
- [ ] Arrow 컴포넌트 구현
- [ ] PulseCircle 컴포넌트 구현
- [ ] Python에서 Remotion CLI 호출 자동화
- [ ] 렌더링된 오버레이와 슬라이드 이미지 합성
