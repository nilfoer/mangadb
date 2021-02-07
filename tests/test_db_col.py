import pytest

from manga_db.db.column import Column, ColumnWithCallback


def event_callback(instance, name, was_unitiialized, before, after):
    if not was_unitiialized:
        instance.events.append(after)


@pytest.fixture
def create_obj_with_col():
    class Obj:
        title = Column(str)
        page = Column(int, primary_key=True)
        event = ColumnWithCallback(str)

        def __init__(self, title=None, page=None, event=None):
            self._committed_state = {}
            self.title = title
            self.page = page
            self.event = event
            self.events = []
            Obj.event.add_callback("event", event_callback)
    yield Obj


def test_db_column(create_obj_with_col):
    Obj = create_obj_with_col

    o = Obj(title="NormalColTest", page=5, event=None)
    # names added to col lists of CLASS
    assert Obj.PRIMARY_KEY_COLUMNS == ["page"]
    assert Obj.COLUMNS == ["title", "event"]
    # init obj shouldnt be counted as changes
    assert not o._committed_state
    o.title = "Altered"
    assert o._committed_state["title"] == "NormalColTest"
    assert "page" not in o._committed_state
    o.title = "Altered Again"
    assert o._committed_state["title"] == "NormalColTest"

    with pytest.raises(TypeError):
        o.page = "wrong type"

    # callback tests
    assert not o.events
    assert o.event is None
    with pytest.raises(TypeError):
        o.event = 10
    assert not o.events
    o.event = "Halloween"
    o.event = "Christmas"
    assert o.events == ["Halloween", "Christmas"]

    # if we create as 2nd instance of Obj the callback that appends to
    # events will already be present when event is initialized
    # self.event = event
    # self.events = []
    # Obj.event.add_callback("event", event_callback)
    # -> tries to append to attr that doesnt exist
    # either make sure the element exists before the descriptors instance is assigned
    # or handle it in the callback by __get__ raising UninitializedColumn
    o = Obj(title="NormalColTest2", page=5, event="ttt")
    assert not o.events
    assert o.event == "ttt"
