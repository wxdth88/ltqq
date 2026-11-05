@echo off
chcp 65001 >nul
echo ==========================================
echo  联通十周年抢QQ超级会员 - 打包工具
echo ==========================================
echo.

echo [1/3] 安装依赖...
pip install -r requirements.txt
if errorlevel 1 (
  echo 依赖安装失败，请检查 Python/pip 是否可用
  pause
  exit /b 1
)

echo.
echo [2/3] 打包成 exe（约 1-3 分钟）...
pyinstaller -F -w --name 联通抢会员 lt_qqsvip_windows.py
if errorlevel 1 (
  echo 打包失败
  pause
  exit /b 1
)

echo.
echo [3/3] 完成！程序在 dist 目录：
echo   dist\联通抢会员.exe
echo.
echo 双击即可运行。首次使用点「登录」获取 Cookie。
echo.
pause