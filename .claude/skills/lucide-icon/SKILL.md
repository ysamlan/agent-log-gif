---
name: lucide-icon
description: >
  Fetch exact Lucide icon SVGs by name from the official repository.
  Use when inserting or replacing a Lucide icon in templates/HTML.
  Triggers: "lucide icon", "add icon", "use the X icon", or any task
  requiring a specific Lucide SVG. Prevents guessing SVG paths from memory.
metadata:
  internal: true
---

# Lucide Icon

Fetch exact SVG markup for Lucide icons from the official repo.

## Usage

Run the script from the skill directory (`lucide-icon/scripts/get_icon.py`):

```bash
# Get an icon by exact name
uv run lucide-icon/scripts/get_icon.py package-open

# Search for icons by keyword
uv run lucide-icon/scripts/get_icon.py --search trash

# Get icon at a specific size
uv run lucide-icon/scripts/get_icon.py package-open --size 16
```

Never guess Lucide SVG paths from memory. Always use this script to get the exact SVG content from the official source.
