"""
Prompt Builder Sanity Test

Runs the current SYSTEM_PROMPT_BUILDER_TEMPLATE against a few sample
Chinese transcripts via Azure OpenAI Chat Completions, then validates
that the output:
  - Is plain text (no markdown/code fences/headings/lists/links)
  - Has a reasonable length (200~1200 chars by default)
  - Avoids obvious formatting symbols (`, #, *, -, [, ], (, ), •)

Usage:
  source .venv/bin/activate
  set -a; source backend/.env; set +a
  python backend/scripts/prompt_sanity.py

Environment:
  AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_API_VERSION,
  AZURE_OPENAI_DEPLOYMENT must be set.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import List, Tuple

from openai import AzureOpenAI

try:
    # Reuse the template from the app
    from backend.app.prompt_templates import SYSTEM_PROMPT_BUILDER_TEMPLATE_MD as BUILDER_TEMPLATE
except Exception:
    raise SystemExit("Failed to import prompt template from backend.app.prompt_templates")


def sanitize_markdown(md: str) -> str:
    s = md or ""
    s = re.sub(r"```", " ", s)  # fenced blocks
    s = re.sub(r"`([^`]+)`", r"\1", s)  # inline code
    s = re.sub(r"^\s{0,3}#{1,6}\s*", "", s, flags=re.M)  # headings
    s = re.sub(r"^\s*[\-\*\+]\s+", "", s, flags=re.M)  # bullets - * +
    s = re.sub(r"^\s*>\s+", "", s, flags=re.M)  # blockquotes
    s = re.sub(r"!\[([^\]]*)\]\([^\)]+\)", r"\1", s)  # images
    s = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", s)  # links
    s = re.sub(r"^\s*---\s*$", "", s, flags=re.M)  # hr
    # Extra: handle common numbered lists and bullets like '•'
    s = re.sub(r"^\s*\d+\.[ \t]+", "", s, flags=re.M)
    s = re.sub(r"^\s*[•·][ \t]+", "", s, flags=re.M)
    # Collapse whitespace
    s = re.sub(r"\r", "\n", s)
    s = re.sub(r"\n{2,}", "\n", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s.strip()


@dataclass
class Sanity:
    length_ok: bool
    markdown_ok: bool
    ascii_ratio_ok: bool
    details: List[str]


MD_PATTERNS = [
    r"```",
    r"^\s{0,3}#{1,6}\s*",
    r"^\s*[\-\*\+]\s+",
    r"\[[^\]]+\]\([^\)]+\)",
    r"\!\[[^\]]*\]\([^\)]+\)",
    r"\*\*[^\*]+\*\*",
]


def validate_plain_text(text: str, min_len: int = 200, max_len: int = 1200) -> Sanity:
    details: List[str] = []
    t = text or ""
    n = len(t)
    length_ok = (min_len <= n <= max_len)
    if not length_ok:
        details.append(f"length={n} not in [{min_len},{max_len}]")

    markdown_hits: List[str] = []
    for p in MD_PATTERNS:
        if re.search(p, t, flags=re.M):
            markdown_hits.append(p)
    markdown_ok = (len(markdown_hits) == 0)
    if not markdown_ok:
        details.append(f"markdown_patterns: {', '.join(markdown_hits)}")

    # Heuristic: ensure majority of characters are non-ASCII (Chinese text),
    # but tolerate numbers and punctuation. Compute ASCII ratio.
    ascii = sum(1 for ch in t if ord(ch) < 128)
    ratio = ascii / (n or 1)
    ascii_ratio_ok = ratio < 0.6
    if not ascii_ratio_ok:
        details.append(f"ascii_ratio={ratio:.2f} too high (should be <0.6)")

    return Sanity(length_ok, markdown_ok, ascii_ratio_ok, details)


SAMPLES: List[str] = [
    """
我在做一款SaaS订阅，面向中小电商。核心功能是订单管理、库存同步和多平台售后。希望Agent用电话或短信联系潜在商家，先了解他们当前的痛点（是否缺数据打通、人工成本高、售后效率低），再介绍我们能带来的效果，比如减少人工操作、降低错单率、拉升复购。语气专业但别太销售，尽量简洁，避免一次问太多问题。
    """.strip(),
    """
我们是线上健身课程平台，目标用户是时间有限的上班族。Agent需要先判断用户更关注减脂、塑形还是提升体能，然后给出匹配的课程路径和试用建议。如果用户担心坚持难或效果慢，要先理解原因再回应，最后给出明确下一步，比如预约试课或领取体验券。
    """.strip(),
]


def main():
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION")
    dep = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    if not all([endpoint, api_key, api_version, dep]):
        raise SystemExit("Missing Azure OpenAI environment variables.")

    client = AzureOpenAI(azure_endpoint=endpoint, api_key=api_key, api_version=api_version)

    print("== Prompt Builder Sanity Test ==\n")
    for i, transcript in enumerate(SAMPLES, 1):
        print(f"[Case {i}] transcript: {transcript[:60]}...")
        resp = client.chat.completions.create(
            model=dep,
            messages=[
                {"role": "system", "content": BUILDER_TEMPLATE},
                {"role": "user", "content": transcript},
            ],
        )
        raw = resp.choices[0].message.content or ""
        clean = sanitize_markdown(raw)
        sanity = validate_plain_text(clean)

        print("  - raw_len:", len(raw), "clean_len:", len(clean))
        print("  - pass length/markdown/ascii:", sanity.length_ok, sanity.markdown_ok, sanity.ascii_ratio_ok)
        if sanity.details:
            print("  - details:", "; ".join(sanity.details))
        print("  - preview:", clean[:120].replace("\n", " "), "...\n")

    print("Done.")


if __name__ == "__main__":
    main()

