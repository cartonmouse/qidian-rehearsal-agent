"""不依赖模型服务的剧本结构化解析工具。

第一阶段使用可解释规则保证本地可运行；Agent 的状态与产出契约保持稳定，后续
可以把其中的实体抽取节点替换为 LLM + 结构化输出，而不改变 API 和领域模型。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.rehearsal.models import DialogueLine, Scene, SourceSpan


_SCENE_RE = re.compile(
    r"^\s*第\s*([0-9一二三四五六七八九十百千]+)\s*场"
    r"(?:\s*[-—:：.]?\s*(.*))?\s*$"
)
_SCENE_EN_RE = re.compile(r"^\s*(?:scene|SCENE)\s*([0-9]+)(?:\s*[-—:：.]?\s*(.*))?\s*$")
_SCENE_LABEL_RE = re.compile(
    r"^\s*场景\s*([0-9一二三四五六七八九十百千]+)?"
    r"(?:\s*[-—:：.]?\s*(.*))?\s*$"
)
_LOCATION_RE = re.compile(r"^\s*(?:内景|外景|INT\.?|EXT\.?)\s*(.*)$", re.IGNORECASE)
_SPEAKER_RE = re.compile(r"^\s*([^\s:：()（）\[\]【】]{1,24})\s*[：:]\s*(.+?)\s*$")

_META_SPEAKERS = {
    "人物",
    "角色",
    "时间",
    "地点",
    "场景",
    "说明",
    "舞台提示",
    "旁白说明",
}
_PROP_LEXICON = (
    "手电筒",
    "信封",
    "纸条",
    "椅子",
    "桌子",
    "剧本",
    "手机",
    "钥匙",
    "箱子",
    "麦克风",
    "话筒",
    "雨伞",
    "行李箱",
    "杯子",
    "书",
    "电脑",
)


@dataclass(frozen=True)
class SceneBlock:
    number: int
    title: str
    start_line: int
    end_line: int
    lines: list[tuple[int, str]]


def _chinese_number(value: str) -> int:
    if value.isdigit():
        return int(value)
    digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    units = {"十": 10, "百": 100, "千": 1000}
    total = 0
    current = 0
    for char in value:
        if char in digits:
            current = digits[char]
        elif char in units:
            total += (current or 1) * units[char]
            current = 0
    return total + current or 1


def normalize_lines(script_text: str) -> list[tuple[int, str]]:
    text = script_text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    return list(enumerate(text.split("\n"), start=1))


def parse_scene_header(text: str) -> tuple[int, str] | None:
    match = _SCENE_RE.match(text)
    if match:
        return _chinese_number(match.group(1)), (match.group(2) or "").strip()

    match = _SCENE_EN_RE.match(text)
    if match:
        return int(match.group(1)), (match.group(2) or "").strip()

    match = _SCENE_LABEL_RE.match(text)
    if match and (match.group(1) or match.group(2)):
        number = _chinese_number(match.group(1)) if match.group(1) else 1
        return number, (match.group(2) or "").strip()

    match = _LOCATION_RE.match(text)
    if match:
        return 1, match.group(1).strip()
    return None


def split_scene_blocks(lines: list[tuple[int, str]]) -> tuple[list[SceneBlock], list[str]]:
    headers: list[tuple[int, int, str]] = []
    for index, (_, text) in enumerate(lines):
        parsed = parse_scene_header(text.strip())
        if parsed:
            headers.append((index, parsed[0], parsed[1]))

    if not headers:
        end_line = lines[-1][0] if lines else 1
        return [SceneBlock(1, "未分场文本", 1, end_line, lines)], [
            "未识别到分场标题，已将全文归入第一场；建议补充“第一场/第二场”等标题。"
        ]

    blocks: list[SceneBlock] = []
    for position, (start_index, number, title) in enumerate(headers):
        end_index = headers[position + 1][0] - 1 if position + 1 < len(headers) else len(lines) - 1
        block_lines = lines[start_index:end_index + 1]
        start_line = block_lines[0][0]
        end_line = block_lines[-1][0]
        blocks.append(SceneBlock(number, title or f"第{number}场", start_line, end_line, block_lines))
    return blocks, []


def is_stage_direction(text: str) -> bool:
    stripped = text.strip()
    return (
        stripped.startswith(("（", "(", "[", "【", "*"))
        or stripped.endswith(("）", ")", "]", "】"))
        or stripped.startswith(("舞台提示", "灯光", "音效"))
    )


def extract_props(text: str) -> list[str]:
    return [prop for prop in _PROP_LEXICON if prop in text]


def extract_scene(block: SceneBlock) -> tuple[Scene, list[str]]:
    scene_id = f"scene-{block.number}"
    characters: list[str] = []
    props: list[str] = []
    lines: list[DialogueLine] = []
    warnings: list[str] = []

    for line_number, raw_text in block.lines:
        text = raw_text.strip()
        if not text or parse_scene_header(text):
            continue

        found_props = extract_props(text)
        for prop in found_props:
            if prop not in props:
                props.append(prop)

        if is_stage_direction(text):
            continue

        match = _SPEAKER_RE.match(text)
        if not match or match.group(1) in _META_SPEAKERS:
            # 首阶段不把无角色前缀的散文误判成台词，保留警告供人工复核。
            continue

        character = match.group(1).strip()
        dialogue = match.group(2).strip()
        if character not in characters:
            characters.append(character)
        lines.append(
            DialogueLine(
                line_id=f"{scene_id}-line-{len(lines) + 1}",
                character=character,
                text=dialogue,
                source=SourceSpan(start_line=line_number, end_line=line_number, excerpt=raw_text.strip()),
            )
        )

    if not lines:
        warnings.append(f"{block.title}未识别到角色台词，请检查角色名和冒号格式。")

    scene = Scene(
        scene_id=scene_id,
        number=block.number,
        title=block.title,
        characters=characters,
        props=props,
        lines=lines,
        source=SourceSpan(
            start_line=block.start_line,
            end_line=block.end_line,
            excerpt="\n".join(text for _, text in block.lines[:3]).strip(),
        ),
    )
    return scene, warnings
