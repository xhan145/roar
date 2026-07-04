import editing


def test_is_scratch_exact_phrases():
    assert editing.is_scratch("scratch that")
    assert editing.is_scratch("Scratch that.")
    assert editing.is_scratch("  SCRATCH IT!  ")
    assert editing.is_scratch("Undo that")


def test_is_scratch_rejects_embedded_and_other():
    assert not editing.is_scratch("please scratch that now")
    assert not editing.is_scratch("scratch that sentence I wrote")
    assert not editing.is_scratch("scratch")
    assert not editing.is_scratch("")
    assert not editing.is_scratch(None)


def test_stack_push_pop_if():
    s = editing.InjectionStack()
    s.push("hello ", 111, 5)
    s.push("world ", 111, 6)
    assert s.pop_if(222) is None            # wrong window -> untouched
    e = s.pop_if(111)
    assert e.typed == "world " and e.history_id == 6
    assert s.pop_if(111).typed == "hello "
    assert s.pop_if(111) is None            # empty


def test_stack_depth_cap():
    s = editing.InjectionStack()
    for i in range(15):
        s.push(f"t{i} ", 1, i)
    seen = []
    while (e := s.pop_if(1)) is not None:
        seen.append(e.history_id)
    assert len(seen) == editing.MAX_DEPTH == 10
    assert seen[0] == 14 and seen[-1] == 5  # oldest 5 dropped
