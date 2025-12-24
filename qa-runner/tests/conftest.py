"""
pytest configuration with complete setup for test-code alignment
"""

import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

TEST_ENV = {
    'QADB_HOST': 'localhost',
    'QADB_PORT': '5432',
    'QADB_NAME': 'qa_test',
    'QADB_USER': 'postgres',
    'QADB_PASSWORD': 'testpass',
    'QADB_CONNECTTIMEOUT': '5',
}

@pytest.fixture(autouse=True)
def setup_test_env():
    """Auto-setup environment for each test"""
    with patch.dict(os.environ, TEST_ENV, clear=False):
        yield

@pytest.fixture
def temp_csv_valid(tmp_path):
    """Create a valid CSV file for testing"""
    csv_file = tmp_path / "orders_valid.csv"
    csv_file.write_text(
        "orderid,customername,orderdate,amounteur,status\n"
        "1,John Doe,2024-01-01,100.00,pending\n"
        "2,Jane Smith,2024-01-02,250.50,completed\n"
        "3,Bob Wilson,2024-01-03,75.25,pending\n",
        encoding='utf-8'
    )
    return str(csv_file)

@pytest.fixture
def temp_csv_empty(tmp_path):
    """Create an empty CSV file"""
    csv_file = tmp_path / "orders_empty.csv"
    csv_file.write_text("", encoding='utf-8')
    return str(csv_file)

@pytest.fixture
def temp_base_dir(tmp_path):
    """Create a temp base directory for file tests"""
    base = tmp_path / "app_local_files"
    base.mkdir()
    (base / "normal.txt").write_text("test")
    (base / "restricted_root_600.txt").write_text("restricted")
    (base / "special@file.txt").write_text("special")
    return str(base)

def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line("markers", "files: tests for files module")
    config.addinivalue_line("markers", "db: tests for database module")
    config.addinivalue_line("markers", "network: tests for network module")
    config.addinivalue_line("markers", "dev: tests for dev module")
    config.addinivalue_line("markers", "integration: integration tests")
    if not hasattr(config.option, 'timeout'):
        config.option.timeout = 30

def pytest_collection_modifyitems(config, items):
    """Auto-add markers based on test file"""
    for item in items:
        fspath = str(item.fspath)
        
        if "test_files.py" in fspath:
            item.add_marker(pytest.mark.files)
        elif "test_database" in fspath:
            item.add_marker(pytest.mark.db)
        elif "test_network" in fspath:
            item.add_marker(pytest.mark.network)
        elif "test_dev" in fspath:
            item.add_marker(pytest.mark.dev)
        
        # Add integration marker for integration tests
        if "Integration" in item.nodeid or "integration" in item.nodeid:
            item.add_marker(pytest.mark.integration)
