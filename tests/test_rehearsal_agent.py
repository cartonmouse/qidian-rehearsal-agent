from pathlib import Path

from backend.rehearsal.agent import ScriptAnalysisAgent


def test_script_agent_extracts_scenes_characters_lines_and_props():
    script = Path("docs/examples/qidian-demo-script.md").read_text(encoding="utf-8")

    result = ScriptAnalysisAgent().run(
        title="轨道之外",
        version_label="v1",
        script_text=script,
    )

    assert [scene.number for scene in result.scenes] == [1, 2]
    assert {character.name for character in result.characters} == {"导演", "小林", "许教授", "小周"}
    assert result.scenes[0].lines[0].text.startswith("所有人先不要急着走位")
    assert {prop.name for prop in result.props} >= {"椅子", "手电筒", "信封", "纸条", "手机"}
    assert [step.name for step in result.trace] == [
        "ingest",
        "split_scenes",
        "extract_entities_parallel",
        "validate",
        "repair",
    ]


def test_script_agent_keeps_source_line_for_human_review():
    result = ScriptAnalysisAgent().run(
        title="短场",
        version_label="v1",
        script_text="第一场\n小林：请把椅子放到这里。",
    )

    line = result.scenes[0].lines[0]
    assert line.source.start_line == 2
    assert line.source.excerpt == "小林：请把椅子放到这里。"


def test_script_agent_repairs_missing_scene_header_conservatively():
    result = ScriptAnalysisAgent().run(
        title="无分场剧本",
        version_label="draft",
        script_text="导演：先读一遍。\n小林：好。",
    )

    assert len(result.scenes) == 1
    assert result.scenes[0].number == 1
    assert any("未识别到分场标题" in warning for warning in result.warnings)
