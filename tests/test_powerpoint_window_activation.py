
from translator.powerpoint_com.adapter import PowerPointComAdapter


class FakeView:
    def __init__(self):
        self.slide = None

    def GotoSlide(self, index):
        self.slide = index


class FakeWindow:
    def __init__(self):
        self.activated = False
        self.View = FakeView()

    def Activate(self):
        self.activated = True


class FakeWindows:
    def __init__(self, window):
        self.window = window

    def __call__(self, index):
        assert index == 1
        return self.window


class FakePresentation:
    def __init__(self):
        self.window = FakeWindow()
        self.Windows = FakeWindows(self.window)


def test_activate_presentation_window():
    presentation = FakePresentation()

    PowerPointComAdapter.activate_presentation_window(
        presentation,
        slide_index=2,
    )

    assert presentation.window.activated is True
    assert presentation.window.View.slide == 2
