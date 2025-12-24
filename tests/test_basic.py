import pytest

class TestBasic:
    @pytest.mark.unit
    def test_simple(self):
        assert 1 + 1 == 2
