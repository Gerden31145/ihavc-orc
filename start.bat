@echo off
echo ======================================
echo 高考分数线 OCR 提取工具
echo ======================================
echo.

echo [1/2] 启动后端 OCR 服务...
start cmd /k "python ocr_api.py"

timeout /t 2 /nobreak >nul

echo [2/2] 启动前端开发服务器...
start cmd /k "npm run dev"

echo.
echo ======================================
echo 服务启动完成！
echo 后端服务: http://localhost:8000
echo 前端服务: http://localhost:5173
echo ======================================
echo.
echo 按任意键关闭此窗口...
pause >nul
