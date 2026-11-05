@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title 联通抢会员 - 一键打包 exe
cd /d "%~dp0"

echo ==========================================
echo   联通抢会员  一键打包 exe
echo ==========================================
echo.

REM ---- 1. 定位 Python ----
python --version >nul 2>&1
if not errorlevel 1 goto :PY_OK

set "PYFOUND="
for %%V in (313 312 311 310 39) do (
    set "CAND=!LOCALAPPDATA!\Programs\Python\Python%%V"
    if exist "!CAND!\python.exe" (
        set "PATH=!CAND!;!CAND!\Scripts;!PATH!"
        set "PYFOUND=1"
    )
)
if defined PYFOUND goto :PY_OK

echo [1/4] 未检测到 Python，正在用 winget 自动安装 Python 3.11...
winget install -e --id Python.Python.3.11 --scope user --accept-source-agreements --accept-package-agreements
if errorlevel 1 (
    echo.
    echo 自动安装失败。请手动下载安装：
    echo     https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
    echo 安装时【务必勾选】"Add python.exe to PATH"，装完重新双击本脚本。
    echo.
    pause
    exit /b 1
)
set "PATH=!LOCALAPPDATA!\Programs\Python\Python311;!LOCALAPPDATA!\Programs\Python\Python311\Scripts;!PATH!"

:PY_OK
echo 当前 Python 版本：
python --version
echo.

echo [2/4] 安装依赖（requests / pywebview / pyinstaller）...
python -m pip install --upgrade pip -q
python -m pip install requests pywebview pyinstaller -q
if errorlevel 1 (
    echo ❌ 依赖安装失败，请检查网络后重试。
    pause
    exit /b 1
)
echo.

echo [3/4] 正在打包 exe（约 1-3 分钟，请勿关闭窗口）...
python -m PyInstaller -F -w --name 联通抢会员 lt_qqsvip_windows.py
if errorlevel 1 (
    echo ❌ 打包失败，请把上面的错误信息截图发我。
    pause
    exit /b 1
)
echo.

echo [4/4] ✅ 打包完成！
echo.
echo exe 位置： %CD%\dist\联通抢会员.exe
echo 正在打开所在文件夹...
start explorer "%CD%\dist"
echo.
pause
exit /b 0