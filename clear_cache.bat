@echo off
REM 캐시 정리 스크립트 (Windows)

echo ==========================================
echo 🗑️  Auto-MPEG 캐시 정리
echo ==========================================
echo.
echo 선택하세요:
echo 1) 전체 삭제 (임시 파일 + 메타데이터 + 최종 영상)
echo 2) 임시 파일만 삭제 (최종 영상 보존)
echo 3) 최종 영상만 삭제 (작업 데이터 보존)
echo 4) 취소
echo.
set /p choice="선택 (1-4): "

if "%choice%"=="1" goto delete_all
if "%choice%"=="2" goto delete_temp
if "%choice%"=="3" goto delete_output
if "%choice%"=="4" goto cancel
goto invalid

:delete_all
echo 🗑️  전체 삭제 중...
if exist data\temp rmdir /s /q data\temp
if exist data\meta rmdir /s /q data\meta
if exist data\output rmdir /s /q data\output
echo ✅ 완료!
goto end

:delete_temp
echo 🗑️  임시 파일 삭제 중...
if exist data\temp rmdir /s /q data\temp
if exist data\meta rmdir /s /q data\meta
echo ✅ 완료! (최종 영상 보존됨)
goto end

:delete_output
echo 🗑️  최종 영상 삭제 중...
if exist data\output rmdir /s /q data\output
echo ✅ 완료! (작업 데이터 보존됨)
goto end

:cancel
echo ❌ 취소됨
goto end

:invalid
echo ❌ 잘못된 선택
goto end

:end
pause
