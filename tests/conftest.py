import pytest
import io

@pytest.fixture
def sample_csv():
    return io.BytesIO(b"id,name\n1,test\n2,demo")
