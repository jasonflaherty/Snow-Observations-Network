from son_core.ids import make_son_id


def test_make_son_id():
    assert make_son_id("us", "nrcs", "301") == "SON-US-NRCS-301"
    assert make_son_id("CA", "BCASWS", "2F05P") == "SON-CA-BCASWS-2F05P"
