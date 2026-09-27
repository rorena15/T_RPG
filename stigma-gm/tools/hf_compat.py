"""transformers 5.5 호환 보정. 모델을 불러오는 스크립트가 transformers를 쓰기 전에 import한다.

LlamaConfig.validate_architecture가 hidden_size % num_attention_heads만 검사해서, head_dim을 따로 지정한
Llama 모델(예: Kanana-1.5-2.1B: hidden 1792, heads 24, head_dim 128)을 잘못 거부한다.
검사 함수는 dataclass 검증 목록에 이미 등록돼 있어 속성만 바꿔서는 안 되므로, 함수 본문(__code__)을 교체한다.
"""


def _validate_llama_architecture(self):
    head_dim = getattr(self, "head_dim", None)
    if head_dim:  # head_dim이 명시되면 hidden_size와 나누어떨어질 필요가 없다
        return
    if self.hidden_size % self.num_attention_heads != 0:
        raise ValueError(
            f"The hidden size ({self.hidden_size}) is not a multiple of the number of attention "
            f"heads ({self.num_attention_heads})."
        )


def patch():
    from transformers.models.llama import configuration_llama
    fn = configuration_llama.LlamaConfig.validate_architecture
    fn.__code__ = _validate_llama_architecture.__code__


patch()
