from translator.powerpoint_com.walker import MSO_GROUP, PowerPointWalker


class Collection:
    def __init__(self, items):
        self._items = list(items)
        self.Count = len(self._items)

    def Item(self, index):
        return self._items[index - 1]


class TextRange:
    def __init__(self, text):
        self.Text = text

    def Replace(self, find, replace, after, match_case, whole_words):
        haystack = self.Text if match_case else self.Text.lower()
        needle = find if match_case else find.lower()
        pos = haystack.find(needle)
        if pos < 0:
            return None
        self.Text = self.Text[:pos] + replace + self.Text[pos + len(find):]
        return self


class TextFrame:
    def __init__(self, text):
        self.TextRange = TextRange(text)


class Shape:
    _next_id = 1

    def __init__(self, name, text=None, shape_type=17, children=None, table=None):
        self.Name = name
        self.Id = Shape._next_id
        Shape._next_id += 1
        self.Type = shape_type
        self.Left = 10
        self.Top = 20
        self.Width = 100
        self.Height = 40
        self.Rotation = 0
        self.HasTable = -1 if table is not None else 0
        self.Table = table
        self.HasTextFrame = -1 if text is not None else 0
        self.TextFrame = TextFrame(text or "")
        self.GroupItems = Collection(children or [])


class Cell:
    def __init__(self, text):
        self.Shape = Shape("cell", text=text)


class Table:
    def __init__(self, rows):
        self._rows = rows
        self.Rows = type("Rows", (), {"Count": len(rows)})()
        self.Columns = type("Columns", (), {"Count": len(rows[0])})()

    def Cell(self, row, col):
        return self._rows[row - 1][col - 1]


class Slide:
    def __init__(self, shapes):
        self.Shapes = Collection(shapes)


class Presentation:
    def __init__(self, slides):
        self.Name = "fake.pptx"
        self.Slides = Collection(slides)


def make_presentation():
    normal = Shape("Normal", text="Shelf life matters")
    grouped_text = Shape("GroupedText", text="Water activity")
    group = Shape("Group", shape_type=MSO_GROUP, children=[grouped_text])
    table = Table([[Cell("Moisture content"), Cell("12%")]])
    table_shape = Shape("Table", table=table, shape_type=19)
    return Presentation([Slide([normal, group, table_shape])])


def test_inspect_reads_normal_group_and_table_text():
    walker = PowerPointWalker()
    stats, elements = walker.inspect(make_presentation())

    assert stats.slide_count == 1
    assert stats.group_count == 1
    assert stats.table_count == 1
    assert stats.table_cell_count == 2
    assert stats.text_shape_count == 2
    assert stats.grouped_text_shape_count == 1
    assert {e.kind for e in elements} == {"text_shape", "group_text", "table_cell"}


def test_replace_first_can_replace_grouped_text():
    walker = PowerPointWalker()
    pres = make_presentation()

    result = walker.replace_first(pres, "Water activity", "Aktivitas air")

    assert result.replaced is True
    assert result.element.kind == "group_text"
    _, elements = walker.inspect(pres)
    assert any(e.text == "Aktivitas air" for e in elements)


def test_structure_snapshot_is_stable_after_text_change():
    walker = PowerPointWalker()
    pres = make_presentation()
    before = walker.structure_snapshot(pres)

    walker.replace_first(pres, "Shelf life", "Umur simpan")
    after = walker.structure_snapshot(pres)

    result = walker.compare_structure(before, after)
    assert result.passed is True
    assert result.differences == []


def test_targeted_replacement_uses_shape_path_and_table_coordinates():
    walker = PowerPointWalker()
    pres = make_presentation()
    _, elements = walker.inspect(pres)

    grouped = next(e for e in elements if e.kind == "group_text")
    assert grouped.shape_path == (2, 1)
    walker.apply_segment_replacements(pres, grouped, [("Water activity", "Aktivitas air")])
    assert walker.read_element_text(pres, grouped) == "Aktivitas air"

    table_cell = next(e for e in elements if e.kind == "table_cell" and e.row == 1 and e.column == 1)
    assert table_cell.shape_path == (3,)
    walker.apply_segment_replacements(pres, table_cell, [("Moisture content", "Kadar air")])
    assert walker.read_element_text(pres, table_cell) == "Kadar air"


def test_inspect_deduplicates_merged_table_cell_aliases():
    walker = PowerPointWalker()
    merged = Cell("Merged heading")
    # Simulate PowerPoint exposing one visible merged cell through 3 coordinates.
    table = Table([[merged, merged, merged], [Cell("A"), Cell("B"), Cell("C")]])
    table_shape = Shape("MergedTable", table=table, shape_type=19)
    pres = Presentation([Slide([table_shape])])

    stats, elements = walker.inspect(pres)
    merged_elements = [e for e in elements if e.text == "Merged heading"]

    assert stats.table_cell_count == 6  # physical coordinates are still counted
    assert len(merged_elements) == 1    # but one visible text cell is translated once
