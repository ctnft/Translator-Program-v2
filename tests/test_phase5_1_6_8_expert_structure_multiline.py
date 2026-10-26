import json

from translator.cache_manager import CacheManager
from translator.expert_profile import ExpertProfileLoader
from translator.powerpoint_com.models import TextElement
from translator.powerpoint_com.semantic_blocks import SemanticTextBlock
from translator.powerpoint_com.translation_service import PowerPointTranslationService
from translator.terminology_lock import TerminologyLock
from translator.translation.engine import TranslationEngine, TranslationRequest
from translator.translation_memory import TranslationMemory


class MultilineClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.num_predict = 256

    def chat_structured(self, *, model, system, user, schema, num_predict_override=None):
        payload = json.loads(user)
        self.calls.append((model, payload, system, schema))
        return self.responses.pop(0)


def _engine(tmp_path, client, *, profile=None):
    return TranslationEngine(
        client=client,
        model="qwen-test",
        translation_memory=TranslationMemory(tmp_path / "tm.db"),
        cache=CacheManager(tmp_path / "cache.db"),
        terminology=TerminologyLock([]),
        domain="food_science",
        prompt_version="phase5168-test",
        terminology_version="test",
        batch_enabled=True,
        batch_size=8,
        fallback_enabled=False,
        expert_profile=profile,
    )


def test_multiline_textbox_uses_one_contextual_call_and_keeps_each_line(tmp_path):
    block = SemanticTextBlock.encode(
        "Agenda Building and Sessions Customization\vAccording to Product Categories Required"
    )
    client = MultilineClient([
        {
            "lines": [
                "Penyusunan Agenda dan Penyesuaian Sesi",
                "Sesuai Kategori Produk yang Diperlukan",
            ]
        }
    ])
    engine = _engine(tmp_path, client)
    request = TranslationRequest(
        text=block.encoded_text,
        slide_context='{"slide":{"role":"agenda"}}',
        context_key="agenda-title",
        semantic_role="slide_title",
        full_element_text=block.flattened_text,
        line_segments=block.line_segments,
        break_tokens=block.break_tokens,
    )

    result = engine.translate_many([request])[0]

    assert client.calls[0][1]["task"] == "translate_multiline_textbox"
    assert client.calls[0][1]["source_lines_for_meaning"] == [
        "Agenda Building and Sessions Customization",
        "According to Product Categories Required",
    ]
    decoded = block.decode(result.target_text)
    assert decoded == (
        "Penyusunan Agenda dan Penyesuaian Sesi\v"
        "Sesuai Kategori Produk yang Diperlukan"
    )


def test_multiline_blank_line_is_retried_instead_of_collapsing_format(tmp_path):
    block = SemanticTextBlock.encode("Training Room\vRequirement")
    client = MultilineClient([
        {"lines": ["Persyaratan Ruang Pelatihan", ""]},
        {"lines": ["Ruang Pelatihan", "Persyaratan"]},
    ])
    engine = _engine(tmp_path, client)
    request = TranslationRequest(
        text=block.encoded_text,
        context_key="training-room-title",
        semantic_role="slide_title",
        full_element_text=block.flattened_text,
        line_segments=block.line_segments,
        break_tokens=block.break_tokens,
    )

    result = engine.translate_many([request])[0]

    assert len(client.calls) == 2
    assert block.decode(result.target_text) == "Ruang Pelatihan\vPersyaratan"
    assert engine.stats["ollama_forced_retry"] == 1


def _cell(slide, shape, row, col, text):
    return TextElement(
        slide_index=slide,
        shape_id=shape,
        shape_name="Table",
        kind="table_cell",
        text=text,
        shape_path=(shape,),
        row=row,
        column=col,
    )


def test_table_structure_disambiguates_stop_and_no_headers():
    elements = [
        _cell(1, 5, 1, 1, "No"),
        _cell(1, 5, 1, 2, "Start"),
        _cell(1, 5, 1, 3, "Stop"),
        _cell(1, 5, 2, 1, "1"),
        _cell(1, 5, 2, 2, "08.00"),
        _cell(1, 5, 2, 3, "08.15"),
        _cell(1, 5, 3, 1, "2"),
        _cell(1, 5, 3, 2, "08.15"),
        _cell(1, 5, 3, 3, "09.00"),
    ]
    contexts = PowerPointTranslationService._build_table_contexts(elements)

    no_ctx = contexts["slide1:shape5:table_cell:r1c1"]
    stop_ctx = contexts["slide1:shape5:table_cell:r1c3"]

    assert no_ctx["semantic_hint"] == "sequence_number_header"
    assert no_ctx["preferred_translation"] == "No."
    assert stop_ctx["semantic_hint"] == "schedule_end_time_header"
    assert stop_ctx["preferred_translation"] == "Selesai"


def test_context_rule_bypasses_bad_tm_for_short_ambiguous_table_header(tmp_path):
    client = MultilineClient([])
    engine = _engine(tmp_path, client)
    # Seed a bad result under another/no structural context.
    engine.tm.save(
        "No",
        "Tidak",
        domain="food_science",
        context_hash="generic",
        source_language="en",
        target_language="id",
        quality_status="machine_validated",
        memory_version=engine.memory_version,
    )

    result = engine.translate(
        "No",
        context_key="generic",
        semantic_role="table_cell",
        structural_hint="sequence_number_header",
        preferred_translation="No.",
    )

    assert result.target_text == "No."
    assert result.origin == "context_rule"
    assert client.calls == []


def test_expert_profile_loader_and_prompt(tmp_path):
    profile_file = tmp_path / "profiles.yaml"
    profile_file.write_text(
        """
profiles:
  sensory:
    role: Senior Sensory Scientist
    experience_standard: Apply 10+ years equivalent judgement.
    expertise:
      - sensory panel training
    decision_rules:
      - Interpret table labels from context.
    terminology_priorities:
      - BPOM
      - SNI
""".strip(),
        encoding="utf-8",
    )
    profile = ExpertProfileLoader().load(profile_file, "sensory")
    client = MultilineClient([{"translation": "Pahit"}])
    engine = _engine(tmp_path, client, profile=profile)

    result = engine.translate("Bitter", context_key="sensory")

    assert result.target_text == "Pahit"
    system = client.calls[0][2]
    assert "Senior Sensory Scientist" in system
    assert "10+ years equivalent" in system
    assert client.calls[0][1]["expert_profile"]["profile_id"] == "sensory"

class _Dimension:
    def __init__(self, *, height=None, width=None):
        self.Height = height
        self.Width = width


class _Dims:
    def __init__(self, values, *, field):
        self._items = [
            _Dimension(height=value) if field == "height" else _Dimension(width=value)
            for value in values
        ]
        self.Count = len(self._items)

    def Item(self, index):
        return self._items[index - 1]


class _TableLayout:
    def __init__(self):
        self.Rows = _Dims([20.0, 30.0, 40.0], field="height")
        self.Columns = _Dims([100.0, 200.0], field="width")


def test_table_row_heights_and_column_widths_can_be_restored():
    from translator.powerpoint_com.walker import PowerPointWalker

    table = _TableLayout()
    state = PowerPointWalker._capture_table_layout(table)
    table.Rows.Item(1).Height = 99.0
    table.Rows.Item(2).Height = 88.0
    table.Columns.Item(1).Width = 333.0

    PowerPointWalker._restore_table_layout(table, state)

    assert [table.Rows.Item(i).Height for i in range(1, 4)] == [20.0, 30.0, 40.0]
    assert [table.Columns.Item(i).Width for i in range(1, 3)] == [100.0, 200.0]
