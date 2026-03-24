# Share URL Format (v1)

Share URLs encode a replay session and rendering options entirely in the URL
fragment, so the web viewer can reconstruct and render a GIF with no server.

```
https://ysamlan.github.io/agent-log-gif/#v1,<options>,<data>
```

The fragment has three comma-separated parts:

| Part | Description |
|------|-------------|
| `v1` | Version tag (literal string) |
| `<options>` | Rendering options — `key=val;key=val`, or empty string for all defaults |
| `<data>` | Base64url-encoded, zlib-compressed JSON event array |

Commas delimit the three top-level parts. The split uses only the **first two**
commas (`split(",", 2)`), so the data segment may contain commas from base64url
(it won't — base64url uses `A-Za-z0-9-_` only — but the split is safe either way).

## Options

Options use short keys. Only non-default values are included; default values
are omitted to save space.

| Short key | Long name | Type | Default | Notes |
|-----------|-----------|------|---------|-------|
| `c` | chrome | string | `mac` | Window chrome style: `none`, `mac`, `mac-square`, `windows`, `linux` |
| `s` | speed | float | `1.0` | Typing speed multiplier |
| `cs` | color_scheme | string | `""` | Terminal color scheme name |
| `l` | loop | bool | `true` | GIF loops infinitely. Encoded as `1`/`0`. |
| `src` | transcript_source | string | `claude` | `claude` or `codex` — affects spinner verbs and shimmer colors |

Booleans are encoded as `1` (true) or `0` (false).

**Not encoded:** `max_turns` and `show` are intentionally excluded. The event
list is already filtered by visibility and sliced to the selected turn range
before encoding — these options are baked into the data.

### Examples

All defaults (empty options):
```
#v1,,eNpLSS0u0U1JTQYADioDBA
```

Custom chrome and no loop:
```
#v1,c=windows;l=0,eNpLSS0u0U1JTQYADioDBA
```

Codex session:
```
#v1,src=codex,eNpLSS0u0U1JTQYADioDBA
```

## Event data

The `<data>` segment encodes the replay events:

### 1. Minimal event format

Events are a JSON array of `[type_code, text]` pairs:

```json
[["u","Create a hello world function"],["a","I'll create that for you."],["tc","Write hello.py"],["a","Done!"]]
```

No metadata, timestamps, session IDs, or tool input dicts. Just the event
type and the display text — the minimum needed to reconstruct the GIF.

#### Type codes

| Code | Event type |
|------|------------|
| `u` | User message |
| `a` | Assistant message |
| `k` | Thinking |
| `tc` | Tool call (text is tool name + hint, e.g. `"Write hello.py"`) |
| `tr` | Tool result |
| `i` | Interrupted |

#### Truncation limits

Long text is truncated before encoding (appending `...`) to keep URLs compact.
These match the animator's display limits:

| Event type | Max chars |
|------------|-----------|
| User message | 500 |
| Assistant message | 800 |
| Thinking | 120 |
| Tool result | 40 |
| Tool call | Not truncated (already short hint strings) |

### 2. JSON serialization

Compact JSON with no whitespace:

```python
json.dumps(events, separators=(",", ":"))
```

### 3. Compression

zlib (RFC 1950) at maximum compression:

```python
zlib.compress(json_bytes, level=9)
```

Browser-side decode uses `DecompressionStream("deflate")` which handles
zlib-wrapped streams natively.

### 4. Base64url encoding

RFC 4648 §5 base64url: `+` → `-`, `/` → `_`, trailing `=` padding stripped.

```python
base64.urlsafe_b64encode(compressed).rstrip(b"=")
```

Decoding re-pads to a multiple of 4 before decoding:

```python
padding = 4 - (len(data_str) % 4)
if padding < 4:
    data_str += "=" * padding
base64.urlsafe_b64decode(data_str)
```

## Encoding pipeline (summary)

```
ReplayEvent list
  → truncate text per limits
  → [[type_code, text], ...] JSON array
  → json.dumps (compact, no whitespace)
  → zlib.compress (level 9)
  → base64url encode (strip padding)
  → assemble: "v1,{options},{encoded}"
```

## Decoding pipeline (summary)

```
URL fragment (after #)
  → split on first two commas → version, options, data
  → validate version == "v1"
  → parse options (key=val;key=val → dict)
  → base64url decode (re-pad =)
  → zlib decompress
  → JSON parse → [[type_code, text], ...]
  → map type codes → ReplayEvent objects
  → render GIF via existing pipeline
```

## Size budget

URLs over 8000 characters are rejected (encoder returns `None`). This is a
conservative limit for broad compatibility across browsers, sharing platforms,
and URL shorteners.

Typical sizes after encoding:

| Session | Approx URL length |
|---------|-------------------|
| 2 turns, short messages | ~200 chars |
| 5 turns, typical | ~600 chars |
| 10 turns, typical | ~1500 chars |
| 20 turns, typical | ~3000 chars |

## Implementations

- **Python (CLI):** `src/agent_log_gif/share.py` — `encode_share_url()`, `decode_share_fragment()`
- **JavaScript (web UI):** `web/index.html` — `encodeShareFragment()`, `decodeShareFragment()`
- **Web pipeline (Pyodide):** `web/pipeline.py` — `render_gif_from_share()` accepts decoded events directly
