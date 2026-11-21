#!/usr/bin/env python3
"""Convert a Hugging Face Llama-architecture model (safetensors + tokenizer.json with a byte-level BPE, e.g.
HuggingFaceTB/SmolLM2-135M-Instruct) into llm.c's files:

  <out>.bin      int8 Q8_0 weights, llama2.c "version 2" layout; extra header fields at byte 64:
                 float rope_theta, int tokenizer type (1 = byte-level BPE + ChatML), int im_start, im_end, eot ids
  <out>.tok      BPE tokenizer: "BPE1", int n_vocab, int max_len, then per token: int len, bytes (raw, not the
                 GPT-2 unicode alias), int merge rank (-1 = not made by a merge), int left id, int right id

numpy only. HF stores q/k for rotate-half RoPE; they are permuted here to llama2.c's interleaved pairs.

    python3 -I convert_hf.py thirdparty/smollm2-135m-instruct smollm2-135m-instruct
"""
import json
import os
import struct
import sys

import numpy as np

GS = 64


def bytes_to_unicode():
    """GPT-2's byte <-> printable-unicode table (byte-level BPE stores tokens with these aliases)."""
    bs = list(range(ord("!"), ord("~") + 1)) + list(range(ord("¡"), ord("¬") + 1)) + list(range(ord("®"), ord("ÿ") + 1))
    cs = bs[:]
    n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return {chr(c): b for b, c in zip(bs, cs)}


def load_safetensors(path):
    f = open(path, "rb")
    n = struct.unpack("<Q", f.read(8))[0]
    hdr = json.loads(f.read(n))
    base = 8 + n
    raw = np.memmap(path, dtype=np.uint8, mode="r")
    out = {}
    for k, v in hdr.items():
        if k == "__metadata__":
            continue
        a, b = v["data_offsets"]
        buf = raw[base + a:base + b]
        if v["dtype"] == "BF16":
            t = (buf.view(np.uint16).astype(np.uint32) << 16).view(np.float32)
        elif v["dtype"] == "F32":
            t = buf.view(np.float32)
        elif v["dtype"] == "F16":
            t = buf.view(np.float16).astype(np.float32)
        else:
            sys.exit(f"unsupported dtype {v['dtype']} for {k}")
        out[k] = t.reshape(v["shape"])
    return out


def unrotate_half(w, n_heads):
    """HF rotate-half row order -> interleaved pairs (inverse of HF's convert_llama_weights permute)."""
    d1, d2 = w.shape
    return w.reshape(n_heads, 2, d1 // n_heads // 2, d2).transpose(0, 2, 1, 3).reshape(d1, d2)


def write_model(src, dst):
    cfg = json.load(open(os.path.join(src, "config.json")))
    W = load_safetensors(os.path.join(src, "model.safetensors"))
    dim, hidden, L = cfg["hidden_size"], cfg["intermediate_size"], cfg["num_hidden_layers"]
    nh, nkv, vocab = cfg["num_attention_heads"], cfg["num_key_value_heads"], cfg["vocab_size"]
    seq_len = cfg["max_position_embeddings"]
    theta = float(cfg.get("rope_theta", 10000.0))
    assert cfg.get("rms_norm_eps", 1e-5) == 1e-5, "llm.c uses eps 1e-5"
    assert not cfg.get("attention_bias") and not cfg.get("mlp_bias")
    shared = cfg.get("tie_word_embeddings", False) or "lm_head.weight" not in W
    lay = lambda i, n: W[f"model.layers.{i}.{n}.weight"]

    tensors = [W["model.embed_tokens.weight"]]
    tensors += [unrotate_half(lay(i, "self_attn.q_proj"), nh) for i in range(L)]
    tensors += [unrotate_half(lay(i, "self_attn.k_proj"), nkv) for i in range(L)]
    tensors += [lay(i, "self_attn.v_proj") for i in range(L)]
    tensors += [lay(i, "self_attn.o_proj") for i in range(L)]
    tensors += [lay(i, "mlp.gate_proj") for i in range(L)]   # w1
    tensors += [lay(i, "mlp.down_proj") for i in range(L)]   # w2
    tensors += [lay(i, "mlp.up_proj") for i in range(L)]     # w3
    if not shared:
        tensors.append(W["lm_head.weight"])

    tok_cfg = json.load(open(os.path.join(src, "tokenizer_config.json")))
    specials = {v["content"]: int(k) for k, v in tok_cfg["added_tokens_decoder"].items()}
    im_start, im_end, eot = specials["<|im_start|>"], specials["<|im_end|>"], specials["<|endoftext|>"]

    with open(dst, "wb") as f:
        hdr = struct.pack("Ii", 0x616B3432, 2) + struct.pack("7i", dim, hidden, L, nh, nkv, vocab, seq_len)
        hdr += struct.pack("B", int(shared)) + struct.pack("i", GS)
        hdr += b"\0" * (64 - len(hdr)) + struct.pack("fiiii", theta, 1, im_start, im_end, eot)
        f.write(hdr + b"\0" * (256 - len(hdr)))
        for n in ("input_layernorm", "post_attention_layernorm"):
            for i in range(L):
                f.write(lay(i, n).astype(np.float32).tobytes())
        f.write(W["model.norm.weight"].astype(np.float32).tobytes())
        maxerr = 0.0
        for t in tensors:
            g = np.ascontiguousarray(t, dtype=np.float32).reshape(-1, GS)
            scale = np.abs(g).max(axis=1) / 127.0
            safe = np.where(scale == 0, 1.0, scale)
            q = np.round(g / safe[:, None]).astype(np.int8)
            maxerr = max(maxerr, float(np.abs(q * scale[:, None] - g).max()))
            f.write(q.tobytes())
            f.write(scale.astype(np.float32).tobytes())
    print(f"dim={dim} hidden={hidden} layers={L} heads={nh}/{nkv} vocab={vocab} rope_theta={theta} "
          f"shared={shared}; wrote {dst} ({os.path.getsize(dst) / 1e6:.1f} MB), max quant error {maxerr:.5f}")
    return vocab


def write_tokenizer(src, dst, n_vocab):
    t = json.load(open(os.path.join(src, "tokenizer.json")))
    m = t["model"]
    assert m["type"] == "BPE" and not m.get("byte_fallback")
    u2b = bytes_to_unicode()
    toks = [b""] * n_vocab
    for s, i in m["vocab"].items():
        toks[i] = bytes(u2b[c] for c in s)
    for a in t.get("added_tokens", []):
        toks[a["id"]] = b""                     # special tokens: never produced from text, never printed
    rank, left, right = [-1] * n_vocab, [-1] * n_vocab, [-1] * n_vocab
    for r, mg in enumerate(m["merges"]):
        a, b = mg.split(" ") if isinstance(mg, str) else mg
        res = m["vocab"][a + b]
        rank[res], left[res], right[res] = r, m["vocab"][a], m["vocab"][b]
    with open(dst, "wb") as f:
        f.write(b"BPE1" + struct.pack("ii", n_vocab, max(len(x) for x in toks)))
        for i in range(n_vocab):
            f.write(struct.pack("i", len(toks[i])) + toks[i] + struct.pack("iii", rank[i], left[i], right[i]))
    print(f"wrote {dst}: {n_vocab} tokens, {len(m['merges'])} merges")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    n = write_model(sys.argv[1], sys.argv[2] + ".bin")
    write_tokenizer(sys.argv[1], sys.argv[2] + ".tok", n)
