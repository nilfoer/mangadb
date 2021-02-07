import pytest

from manga_db.db.column_associated import trackable_type, AssociatedColumnOne, AssociatedColumnMany
from manga_db.db.constants import Relationship


def event_callback(instance, name, was_unitiialized, before, after):
    if not was_unitiialized:
        instance.changes[name] = before, after


@pytest.fixture
def create_obj_with_col_assoc():
    class Obj:
        parent = AssociatedColumnOne("ParentTable", Relationship.MANYTOONE)
        tags = AssociatedColumnMany("Tag", Relationship.MANYTOMANY, assoc_table="ObjTag")
        childs = AssociatedColumnMany("Childs", Relationship.ONETOMANY)

        def __init__(self, parent=None, tags=None, childs=None):
            self._committed_state = {}
            self.changes = {}
            self.parent = parent
            Obj.parent.add_callback("parent", event_callback)
            self.tags = tags
            Obj.tags.add_callback("tags", event_callback)
            self.childs = childs
            Obj.childs.add_callback("childs", event_callback)
    yield Obj


def test_assoc_col(create_obj_with_col_assoc):
    Obj = create_obj_with_col_assoc

    assert Obj.ASSOCIATED_COLUMNS == ["parent", "tags", "childs"]
    o = Obj(11, ["Test", "Docs", "New"], None)
    # init doesnt count as change
    assert not o._committed_state

    o.parent = 333
    assert o.parent == 333
    assert o._committed_state["parent"] == 11
    assert o.changes["parent"] == (11, 333)

    o.tags = ["Test", "Docs"]
    assert o.tags == ["Test", "Docs"]
    assert o._committed_state["tags"] == ["Test", "Docs", "New"]
    assert o.changes["tags"] == (["Test", "Docs", "New"], ["Test", "Docs"])

    # assoc col many is never none since it gets the trackable type assigned
    # or handle it in the callback by __get__ raising UninitializedColumn
    assert o.childs == []
    o.childs = [1, 2, 3]
    assert o.childs == [1, 2, 3]
    assert o._committed_state["childs"] == []
    assert o.changes["childs"] == ([], [1, 2, 3])

    # CAREFUL!
    # if we create a 2nd instance of e.g. Obj that contains this cls the callback that appends to
    # events will already be present when event is initialized
    # Obj __init__:
    # self.event = event
    # self.events = []
    # Obj.event.add_callback("event", event_callback)
    # -> tries to append to attr that doesnt exist
    # either make sure the element exists before the descriptors instance is assigned
    # or handle it in the callback by __get__ raising UninitializedColumn
    o = Obj(11, ["Test", "Docs", "New"], None)
    assert not o.changes


def on_change_callback(instance, name, was_unitiialized, before, after):
    instance.revisions.append(before)


def test_trackable_type():
    class WithTrackable:
        def __init__(self):
            self.trackable = trackable_type(self, "trackable", list, on_change_callback)
            self.revisions = []
    o = WithTrackable()
    assert not o.revisions
    o.trackable.append(1)
    assert o.trackable == [1]
    assert o.revisions == [[]]
    o.trackable.append(2)
    assert o.trackable == [1, 2]
    assert o.revisions == [[], [1]]
    o.trackable.extend(range(3, 6))
    assert o.trackable == [1, 2, 3, 4, 5]
    assert o.revisions == [[], [1], [1, 2]]
    o.trackable.remove(2)
    assert o.trackable == [1, 3, 4, 5]
    assert o.revisions == [[], [1], [1, 2], [1, 2, 3, 4, 5]]
    o.trackable.reverse()
    assert o.trackable == [5, 4, 3, 1]
    assert o.revisions == [[], [1], [1, 2], [1, 2, 3, 4, 5], [1, 3, 4, 5]]


