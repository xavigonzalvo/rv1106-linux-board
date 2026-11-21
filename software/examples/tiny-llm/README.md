# tiny-llm — a 135M-parameter chat model on the board's CPU

**SmolLM2-135M-Instruct** (Hugging Face, Apache-2.0; Llama architecture: dim 576, 30 layers, 9 query / 3 KV heads,
49 152-token vocabulary) runs int8 on the RV1106's single Cortex-A7, no NPU. Type a message in the board's shell
and it answers at about 2.5 tokens/s.

| Part | What | Where on the board |
|---|---|---|
| `llm.c` | from `runq.c` in karpathy/llama2.c (MIT, `LICENSE-llama2.c`), changed to fit in RAM and to run Hugging Face models; NEON int8 dot product with prefetch | `/root/tiny-llm/llm` |
| `convert_hf.py` | Hugging Face safetensors + `tokenizer.json` → int8 `.bin` + BPE `.tok`, numpy only | runs on the Mac |
| `chat` | wrapper: `chat [context tokens] ["system prompt"]` | `/usr/bin/chat` |
| model + tokenizer | `smollm2-135m-instruct.bin` (143 MB), `smollm2-135m-instruct.tok` (1.1 MB) | `/mnt/sdcard/tiny-llm/` |

## Install / run (from the Mac, board on USB, microSD inserted)

```sh
sh software/examples/tiny-llm/deploy.sh
adb shell          # then, on the board:
chat               # type a message + Enter; /quit or Ctrl-D to leave
```
`chat 768` for a longer conversation; `chat 512 "You are a pirate."` for your own system prompt.
The model download (257 MB) and conversion happen once, into `thirdparty/smollm2-135m-instruct/` (git-ignored).

## On the board (board #1, Luckfox image, 2026-11-21)

```
> What is the capital of France?
The capital of France is Paris.
[prompt 37 tok 11.0 s, reply 7 tok 2.6 tok/s, context 44/512]
> Give me three tips to sleep better.
1. Create a relaxing bedtime routine. ...  2. Create a sleep-conducive environment. ...
3. Limit exposure to screens before bedtime. ...
[prompt 19 tok 5.9 s, reply 84 tok 2.5 tok/s, context 147/512]
```

* **2.5–2.6 tok/s** for short replies, slower as the conversation grows (attention reads every earlier token):
  2.0 tok/s averaged over a 474-token reply, 1.7 over 730. The prompt is read at ~3.3 tok/s (no vocab matmul for
  prompt tokens); the default system prompt + first question is 37 tokens, so the first answer starts after ~11 s.
* **Memory** (peak RSS, conversation filled to the end, ai-detect running alongside, 164 MB available):

  | `chat` context | peak RSS | |
  |---|---|---|
  | 512 (default) | 155 MB | weights 143 MB + fp16 KV cache 11.8 MB (~23 kB per token) |
  | 768 | 160 MB | still no page-ins from the card (99 % CPU), ~3 MB to spare |

  More than ~768 will push the weights out of RAM and every token re-reads the microSD; stop ai-detect
  (`/etc/init.d/S99ai-detect stop`) if you need the room.
* **Cold start 20 s** (after `drop_caches`): llm.c reads the model file once, sequentially, before running. Without
  that read the mmap faulted the model in 4 kB at a time from the card: 228 s and 26 000 major page faults.
* The whole conversation shares the `-n` budget; when it is full, `chat` says so and exits.
* It is a 135M model: fine for short factual answers, lists and simple rewrites; it makes up facts easily.
* Tested with input piped in (`printf "...\n" | llm ... -m chat`), not yet by typing in an interactive `adb shell`.

## What llm.c changes from upstream runq.c

| Change | Why |
|---|---|
| token embedding stays int8 in the mmap, one row dequantized per token | upstream makes a fp32 copy (+113 MB here) |
| KV cache sized for `-n` steps and stored as fp16 | upstream: fp32 for the full 8192-token context |
| no classifier matmul for prompt tokens | 21 % of the weights are the 49 152 × 576 classifier |
| model file read sequentially at start | 228 s → 20 s cold start from the microSD |
| NEON int8 dot product + `__builtin_prefetch` 1 kB ahead | see speed notes below |
| RoPE theta from the header, byte-level BPE tokenizer, ChatML chat loop | to run Hugging Face models |
| removed: sentencepiece tokenizer, upstream generate/chat loops | only needed for llama2.c's own models |

**Speed notes** (measured earlier with Karpathy's stories110M, 116 MB, `-n 64`): plain C 2.21 tok/s, NEON 2.34,
NEON + prefetch 128 / 256 / 512 / **1024** / 2048 / 4096 B ahead 3.21 / 3.39 / 3.43 / **3.47** / 3.44 / 3.42.
Inference here is memory-bound: every token streams all weights through the A7, NEON math alone gave only +6 %,
and asking for the weights early gave +48 % (`LLM_PREFETCH` in `llm.c`).

## How the conversion was checked (on the Mac)

| | how | checked |
|---|---|---|
| tokenizer | GPT-2 byte-level BPE (49 152 tokens, 48 900 merges), GPT-2 regex pre-split + single digits; merges by exact rank | same ids as Hugging Face `tokenizers` on 22 strings (Unicode, emoji, code, numbers, contractions, whitespace) |
| q/k weights | HF rotate-half RoPE layout permuted to llama2.c interleaved pairs; RoPE theta 100 000 in the header | int8 C output = independent numpy fp32 reference of the HF model, 40 greedy tokens identical |
| chat format | ChatML: `<\|im_start\|>role\ncontent<\|im_end\|>\n`, special tokens inserted as ids | answers stop cleanly at `<\|im_end\|>` |

Test hook: `LLM_SHOW_TOKENS=1 llm model.bin -i "text"` prints the token ids and exits.
