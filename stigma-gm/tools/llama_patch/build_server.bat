@echo off
rem Build the decrypting llama-server as ONE exe (Vulkan + CPU backends statically linked).
rem Backend DLLs could be swapped for a fake ggml-vulkan.dll that dumps uploaded weights, so link statically.
rem Needs: VS 2022 (MSVC + bundled CMake/Ninja), Vulkan SDK, stigma.patch applied, stigma-key.inc from model_crypt.py emit
rem   tools\llama_patch\build_server.bat  [source dir, default E:\Git_Project\stigma-train\toolchain\llama.cpp-stigma]
rem Keep this file ASCII only: cmd misparses UTF-8 Korean lines.
setlocal
set SRC=%~1
if "%SRC%"=="" set SRC=E:\Git_Project\stigma-train\toolchain\llama.cpp-stigma
if not exist "%SRC%\ggml\src\stigma-key.inc" (
  echo missing stigma-key.inc: python tools\model_crypt.py emit --tag models-v1
  exit /b 1
)
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
set "VSCMAKE=C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake"
set "PATH=%VSCMAKE%\CMake\bin;%VSCMAKE%\Ninja;%PATH%"
if "%VULKAN_SDK%"=="" for /d %%d in (C:\VulkanSDK\*) do set "VULKAN_SDK=%%d"
set "PATH=%VULKAN_SDK%\Bin;%PATH%"

rem LLAMA_SUBPROCESS=OFF drops the server's file/shell tools and router mode (less attack surface)
cmake -S "%SRC%" -B "%SRC%\build-stigma" -G Ninja ^
  -DCMAKE_BUILD_TYPE=Release ^
  -DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded ^
  -DBUILD_SHARED_LIBS=OFF ^
  -DGGML_BACKEND_DL=OFF ^
  -DGGML_VULKAN=ON ^
  -DGGML_NATIVE=OFF -DGGML_AVX2=ON -DGGML_FMA=ON -DGGML_F16C=ON ^
  -DGGML_OPENMP=OFF ^
  -DLLAMA_OPENSSL=OFF ^
  -DLLAMA_SUBPROCESS=OFF ^
  -DLLAMA_USE_PREBUILT_UI=OFF -DLLAMA_BUILD_UI=OFF ^
  -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_APP=OFF || exit /b 1
cmake --build "%SRC%\build-stigma" --target llama-server -j || exit /b 1
echo built: %SRC%\build-stigma\bin\llama-server.exe
