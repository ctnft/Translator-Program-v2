import json

from translator.cache_manager import CacheManager
from translator.powerpoint_com.models import TextElement
from translator.powerpoint_com.walker import PowerPointWalker
from translator.terminology_lock import TerminologyLock
from translator.translation.engine import TranslationEngine
from translator.translation_memory import TranslationMemory


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.num_predict = 256

    def chat_structured(self, *, model, system, user, schema, num_predict_override=None):
        self.calls.append(json.loads(user))
        return self.responses.pop(0)


def make_engine(tmp_path, client, terms):
    return TranslationEngine(
        client=client,
        model="primary",
        translation_memory=TranslationMemory(tmp_path / "tm.db"),
        cache=CacheManager(tmp_path / "cache.db"),
        terminology=TerminologyLock(terms),
        domain="food_science",
        prompt_version="phase5166-test",
        terminology_version="1.6-test",
        batch_enabled=False,
    )


def test_glossary_guidance_comes_only_from_current_element_not_slide_context(tmp_path):
    client = FakeClient([{"translation": "Pahit"}])
    terms = [{"source": "Off Note", "target": "Rasa Menyimpang", "status": "locked"}]
    engine = make_engine(tmp_path, client, terms)

    result = engine.translate(
        "Bitter",
        slide_context='{"slide":{"title":"Recommended Off Note List"}}',
        context_key="ctx",
        semantic_role="table_cell",
        full_element_text="Bitter",
    )

    assert result.target_text == "Pahit"
    assert client.calls[0]["authoritative_terminology"] == []


def test_terminology_target_injection_is_retried(tmp_path):
    client = FakeClient([
        {"translation": "Rasa Menyimpang"},
        {"translation": "Pahit"},
    ])
    terms = [{"source": "Off Note", "target": "Rasa Menyimpang", "status": "locked"}]
    engine = make_engine(tmp_path, client, terms)

    result = engine.translate("Bitter", context_key="ctx", semantic_role="table_cell")

    assert result.target_text == "Pahit"
    assert len(client.calls) == 2
    assert engine.stats["ollama_forced_retry"] == 1


def test_extra_duplicate_glossary_target_is_rejected(tmp_path):
    client = FakeClient([
        {"translation": "Danone Rasa Menyimpang/Rasa Menyimpang"},
        {"translation": "Danone Rasa Menyimpang/Atribut"},
    ])
    terms = [{"source": "Off Note", "target": "Rasa Menyimpang", "status": "locked"}]
    engine = make_engine(tmp_path, client, terms)

    result = engine.translate(
        "Danone Off Note/Attribute",
        context_key="ctx",
        semantic_role="table_cell",
        full_element_text="Danone Off Note/Attribute",
    )

    assert result.target_text == "Danone Rasa Menyimpang/Atribut"
    assert len(client.calls) == 2


class FontColor:
    def __init__(self, rgb):
        self.RGB = rgb


class FontProxy:
    PROPS = ("Name", "Size", "Bold", "Italic", "Underline", "Shadow", "Emboss", "BaselineOffset")

    def __init__(self, styles, start, length):
        object.__setattr__(self, "styles", styles)
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "length", length)
        first = styles[start] if styles and start < len(styles) else {}
        object.__setattr__(self, "Color", FontColor(first.get("ColorRGB", 0)))

    def __getattr__(self, name):
        if name in self.PROPS:
            return self.styles[self.start].get(name)
        raise AttributeError(name)

    def __setattr__(self, name, value):
        if name in self.PROPS:
            for i in range(self.start, min(len(self.styles), self.start + self.length)):
                self.styles[i][name] = value
            return
        if name == "Color":
            object.__setattr__(self, name, value)
            return
        object.__setattr__(self, name, value)


class RangeView:
    def __init__(self, owner, start, length):
        self.owner = owner
        self.start = start
        self.length = length
        self.Font = FontProxy(owner.styles, start, length)


class StyledTextRange:
    def __init__(self, text, styles, shape):
        self.Text = text
        self.styles = [dict(x) for x in styles]
        self.shape = shape
        self.Characters = self._characters

    def _characters(self, start, length):
        return RangeView(self, start - 1, length)

    def Replace(self, find, replace, after, match_case, whole_words):
        pos = self.Text.find(find)
        if pos < 0:
            return None
        inherited = dict(self.styles[pos]) if self.styles else {}
        self.Text = self.Text[:pos] + replace + self.Text[pos + len(find):]
        self.styles[pos:pos + len(find)] = [dict(inherited) for _ in replace]
        # Simulate PowerPoint auto-size geometry drift if writer forgot to freeze it.
        if self.shape.TextFrame.AutoSize != 0:
            self.shape.Width += 25
            self.shape.Height += 10
        return self


class TextFrame:
    def __init__(self):
        self.AutoSize = 1
        self.WordWrap = -1
        self.MarginLeft = 3
        self.MarginRight = 3
        self.MarginTop = 2
        self.MarginBottom = 2
        self.VerticalAnchor = 1
        self.TextRange = None


class Collection:
    def __init__(self, items):
        self.items = items
        self.Count = len(items)

    def Item(self, index):
        return self.items[index - 1]


class Shape:
    def __init__(self):
        self.Left = 10
        self.Top = 20
        self.Width = 300
        self.Height = 80
        self.Rotation = 0
        self.TextFrame = TextFrame()
        self.TextFrame2 = None
        self.GroupItems = Collection([])


class Slide:
    def __init__(self, shape):
        self.Shapes = Collection([shape])


class Presentation:
    def __init__(self, shape):
        self.Slides = Collection([Slide(shape)])


def _style(size, name, rgb, bold=0):
    return {
        "Name": name,
        "Size": size,
        "Bold": bold,
        "Italic": 0,
        "Underline": 0,
        "Shadow": 0,
        "Emboss": 0,
        "BaselineOffset": 0,
        "ColorRGB": rgb,
    }


def test_writer_freezes_geometry_and_reapplies_line_font_styles():
    source = "Safety\rInduction"
    shape = Shape()
    first = _style(20, "Aptos", 111, bold=-1)
    second = _style(32, "Arial", 222, bold=0)
    styles = [first] * len("Safety") + [_style(20, "Aptos", 111)] + [second] * len("Induction")
    shape.TextFrame.TextRange = StyledTextRange(source, styles, shape)
    pres = Presentation(shape)
    element = TextElement(
        slide_index=1,
        shape_id=1,
        shape_name="Title",
        kind="text_shape",
        text=source,
        shape_path=(1,),
    )
    walker = PowerPointWalker()
    before_geometry = (shape.Left, shape.Top, shape.Width, shape.Height)

    result = walker.apply_segment_replacements(
        pres,
        element,
        [("Safety", "Induksi"), ("Induction", "Keselamatan")],
    )

    assert result == "Induksi\rKeselamatan"
    assert (shape.Left, shape.Top, shape.Width, shape.Height) == before_geometry
    assert shape.TextFrame.AutoSize == 0

    # First translated line inherits the original first-line style.
    first_styles = shape.TextFrame.TextRange.styles[:len("Induksi")]
    assert all(s["Size"] == 20 and s["Name"] == "Aptos" and s["ColorRGB"] == 111 for s in first_styles)
    # Skip the paragraph break, then verify the second line's distinct original style.
    start2 = len("Induksi") + 1
    second_styles = shape.TextFrame.TextRange.styles[start2:start2 + len("Keselamatan")]
    assert all(s["Size"] == 32 and s["Name"] == "Arial" and s["ColorRGB"] == 222 for s in second_styles)

def test_writer_preserves_mixed_font_run_pattern_inside_same_line():
    source = "ABCD"
    shape = Shape()
    a = _style(14, "Aptos", 111, bold=-1)
    b = _style(24, "Arial", 222, bold=0)
    shape.TextFrame.TextRange = StyledTextRange(source, [a, a, b, b], shape)
    pres = Presentation(shape)
    element = TextElement(
        slide_index=1,
        shape_id=1,
        shape_name="Mixed",
        kind="text_shape",
        text=source,
        shape_path=(1,),
    )

    result = PowerPointWalker().apply_segment_replacements(
        pres,
        element,
        [("ABCD", "ABCDEFGH")],
    )

    assert result == "ABCDEFGH"
    styles = shape.TextFrame.TextRange.styles
    assert [s["Size"] for s in styles[:4]] == [14, 14, 14, 14]
    assert [s["Size"] for s in styles[4:8]] == [24, 24, 24, 24]
    assert [s["Name"] for s in styles[:4]] == ["Aptos"] * 4
    assert [s["Name"] for s in styles[4:8]] == ["Arial"] * 4


class SideEffectBullet:
    """Simulate PowerPoint re-enabling bullets when Type/Character is assigned."""

    def __init__(self, visible=0, bullet_type=1, character=8226):
        object.__setattr__(self, "Visible", visible)
        object.__setattr__(self, "Type", bullet_type)
        object.__setattr__(self, "Character", character)
        object.__setattr__(self, "RelativeSize", 1.0)
        object.__setattr__(self, "UseTextColor", -1)
        object.__setattr__(self, "UseTextFont", -1)

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)
        if name in {"Type", "Character", "RelativeSize", "UseTextColor", "UseTextFont"}:
            object.__setattr__(self, "Visible", -1)


class ParagraphFormatProxy:
    def __init__(self, bullet):
        self.Alignment = 1
        self.BaseLineAlignment = 0
        self.SpaceBefore = 0
        self.SpaceAfter = 0
        self.SpaceWithin = 1
        self.Bullet = bullet


def test_non_bullet_signature_never_replays_type_or_character():
    walker = PowerPointWalker()
    source_bullet = SideEffectBullet(visible=0, bullet_type=2, character=9679)
    source_format = ParagraphFormatProxy(source_bullet)

    signature = walker._paragraph_signature(source_format)

    assert signature["Bullet"] == {"Visible": False}

    # Target starts with a bogus bullet. Restoring a non-bulleted source paragraph
    # must switch it off without touching properties that can turn it on again.
    target_bullet = SideEffectBullet(visible=-1, bullet_type=9, character=9733)
    target_format = ParagraphFormatProxy(target_bullet)
    walker._apply_paragraph_signature(target_format, signature)

    assert target_bullet.Visible == 0
    assert target_bullet.Type == 9
    assert target_bullet.Character == 9733


def test_real_bullet_is_restored_and_visible_only_after_details():
    walker = PowerPointWalker()
    source_bullet = SideEffectBullet(visible=-1, bullet_type=1, character=8226)
    signature = walker._paragraph_signature(ParagraphFormatProxy(source_bullet))

    target_bullet = SideEffectBullet(visible=0, bullet_type=7, character=9679)
    target_format = ParagraphFormatProxy(target_bullet)
    walker._apply_paragraph_signature(target_format, signature)

    assert target_bullet.Visible == -1
    assert target_bullet.Type == 1
    assert target_bullet.Character == 8226


def test_soft_line_break_is_not_treated_as_new_paragraph_for_bullet_formatting():
    walker = PowerPointWalker()
    assert walker._paragraph_offsets("Safety\vInduction") == [(0, len("Safety\vInduction"))]
    assert walker._paragraph_offsets("Line 1\rLine 2") == [(0, 6), (7, 13)]
