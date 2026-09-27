"""llama.cpp의 convert_hf_to_gguf.py를 hf_compat 보정(transformers 5.5 head_dim 버그)을 적용한 채 실행한다.

변환 스크립트가 토크나이저를 읽으려고 transformers를 쓰는데, head_dim을 따로 지정한 모델(Kanana 2.1B)을 거부하기 때문.
  실행:  python tools/convert_gguf.py <llama.cpp 폴더> <convert_hf_to_gguf.py 인자...>
"""
import os
import runpy
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hf_compat  # noqa: E402,F401

llama_cpp = sys.argv[1]
script = os.path.join(llama_cpp, "convert_hf_to_gguf.py")
sys.argv = [script] + sys.argv[2:]
sys.path.insert(0, llama_cpp)
runpy.run_path(script, run_name="__main__")
