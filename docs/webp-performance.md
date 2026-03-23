# WebP Performance Analysis

WebP doesn't offer a compelling advantage over GIF for most users. GIF gives you universal compatibility with good-enough quality. AVIF gives you tiny files when you have ffmpeg. WebP lands in an awkward middle: slightly better fidelity than GIF, but at the cost of additional dependencies and slower encoding. Unless pixel-perfect output matters to you, GIF or AVIF are the better choices.

## Benchmark Results

Tested with synthetic terminal sessions at 3 sizes. GIF uses gifsicle `--lossy=80` (our default). AVIF uses ffmpeg/libsvtav1 crf=30. WebP modes tested via `img2webp` (libwebp 1.5.0) and Pillow.

### File Size

| Config | 3 turns (132 fr) | 10 turns (441 fr) | 20 turns (891 fr) |
|--------|------------------:|-------------------:|-------------------:|
| GIF lossy=80 | 584 KB (100%) | 2.2 MB (100%) | 4.7 MB (100%) |
| AVIF crf=30 | 102 KB (17%) | 326 KB (14%) | 631 KB (13%) |
| WebP lossless (Pillow) | 925 KB (158%) | 3.2 MB (143%) | 6.4 MB (138%) |
| WebP near-lossless=0 | 649 KB (111%) | 2.3 MB (104%) | 4.7 MB (102%) |
| WebP lossy q=50 | 591 KB (101%) | 2.2 MB (100%) | 4.6 MB (99%) |

### Encoding Speed (wall time including PNG frame I/O)

| Config | 3 turns | 10 turns | 20 turns |
|--------|--------:|---------:|---------:|
| GIF lossy=80 | 1.3s | 4.6s | 9.4s |
| AVIF crf=30 | 8.9s | 28.3s | 54.8s |
| WebP lossless (Pillow) | 1.8s | 6.6s | 13.3s |
| WebP near-lossless=0 (img2webp) | 2.3s | 8.7s | 18.3s |
| WebP lossy q=50 (img2webp) | 1.9s | 7.4s | 15.7s |

### Quality (PSNR vs original frames)

| Config | 3 turns | 10 turns | 20 turns |
|--------|--------:|---------:|---------:|
| GIF lossy=80 | 27.7 dB | 25.4 dB | 25.6 dB |
| AVIF crf=30 | 31.5 dB | 26.5 dB | 22.8 dB |
| WebP lossless | ∞ | ∞ | ∞ |
| WebP near-lossless=0 | 30.9 dB | 27.3 dB | 27.5 dB |
| WebP lossy q=50 | 30.1 dB | 26.5 dB | 26.7 dB |

## Analysis

**GIF** is the practical default: fast encoding, universal support, no external dependencies beyond the optional gifsicle. Quality is good enough for terminal content — the 256-color palette quantization is the main fidelity loss, but text remains readable.

**AVIF** is for size-sensitive use cases: 7-10x smaller than GIF, but 5-10x slower to encode, and requires ffmpeg with an AV1 encoder.

**WebP** occupies a narrow niche:
- **Lossless WebP** (Pillow, no extra deps) is 40-60% larger than GIF. The only advantage is bit-perfect fidelity — useful for archival or pixel-level comparison, but the files are big.
- **Near-lossless** (requires `img2webp` from libwebp) gets within ~2-10% of GIF size with 2+ dB better PSNR. This is the best WebP mode for terminal content, but it adds a dependency and is ~2x slower than the GIF pipeline due to intermediate PNG file I/O.
- **Lossy WebP q=50** matches GIF size with comparable quality — no real advantage.

### When to use WebP

- You need lossless output and can tolerate larger files
- You need better-than-GIF fidelity without the encoding cost of AVIF
- Your target platform prefers WebP over GIF (some messaging apps, web embedding)

### Dependencies

WebP output via Pillow works with no extra dependencies (lossless only, larger files). For near-lossless encoding with competitive file sizes, install libwebp tools (`img2webp`, `cwebp`) — see [the libwebp downloads page](https://developers.google.com/speed/webp/download). These are installed in the devcontainer by default.

## Methodology

Frames generated via `scripts/benchmark_formats.py` using synthetic multi-turn sessions with `TerminalRenderer` at default theme (804×502). PSNR computed by decoding output files and comparing against original RGB frames at 4 sample points per session. All tests on the same machine in sequence.
