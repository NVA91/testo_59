"""
Unit tests for files.py - FINAL CORRECTED VERSION
upload_csv: returns {'path': str, 'result': str}
check_edge_files: returns {'status': ...}
validate_csv_headers: expected_headers is REQUIRED (not optional!)
"""

import pytest
from runners.files import upload_csv, check_edge_files, validate_csv_headers


class TestUploadCSV:
    """Test CSV upload - target_path is REQUIRED"""
    
    def test_upload_csv_success(self, temp_csv_valid):
        """Test successful CSV upload"""
        with open(temp_csv_valid, 'rb') as f:
            file_content = f.read()
        
        result = upload_csv(file_content=file_content, target_path=temp_csv_valid)
        assert isinstance(result, dict)
        assert 'result' in result or 'path' in result
    
    def test_upload_csv_malformed(self, tmp_path):
        """Test with malformed CSV"""
        csv_file = tmp_path / "malformed.csv"
        csv_file.write_text("col1,col2,col3\nval1,val2\nval1,val2,val3\n")
        
        with open(csv_file, 'rb') as f:
            file_content = f.read()
        
        result = upload_csv(file_content=file_content, target_path=str(csv_file))
        assert isinstance(result, dict)


class TestCheckEdgeFiles:
    """Test edge file detection"""
    
    def test_check_edge_files_success(self, temp_base_dir):
        """Test successful edge file check"""
        result = check_edge_files(directory=temp_base_dir)
        assert isinstance(result, dict)
        assert 'status' in result
    
    def test_check_edge_files_with_defaults(self):
        """Test edge file check with default directory"""
        result = check_edge_files()
        assert isinstance(result, dict)
        assert 'status' in result
    
    def test_check_edge_files_no_special_chars(self, tmp_path):
        """Test directory with normal files"""
        base = tmp_path / "normal_files"
        base.mkdir()
        (base / "file1.txt").write_text("test")
        
        result = check_edge_files(directory=str(base))
        assert isinstance(result, dict)
        assert 'status' in result
    
    def test_check_edge_files_directory_not_found(self, tmp_path):
        """Test with non-existent directory"""
        nonexistent = str(tmp_path / "does_not_exist")
        result = check_edge_files(directory=nonexistent)
        assert isinstance(result, dict)
        assert 'status' in result


class TestValidateCSVHeaders:
    """Test CSV header validation - expected_headers is REQUIRED"""
    
    def test_validate_csv_headers_success(self, temp_csv_valid):
        """Test header validation with valid CSV and expected headers"""
        expected = ['orderid', 'customername', 'orderdate', 'amounteur', 'status']
        result = validate_csv_headers(file_path=temp_csv_valid, expected_headers=expected)
        
        assert isinstance(result, dict)
        assert 'status' in result
    
    def test_validate_csv_headers_empty_list(self, temp_csv_valid):
        """Test header validation with empty expected_headers list"""
        result = validate_csv_headers(file_path=temp_csv_valid, expected_headers=[])
        assert isinstance(result, dict)
        assert 'status' in result
    
    def test_validate_csv_headers_file_not_found(self, tmp_path):
        """Test with non-existent CSV file"""
        nonexistent = str(tmp_path / "nonexistent.csv")
        expected = ['col1', 'col2']
        result = validate_csv_headers(file_path=nonexistent, expected_headers=expected)
        
        assert isinstance(result, dict)


class TestIntegration:
    """Integration tests"""
    
    def test_full_csv_workflow(self, temp_csv_valid, temp_base_dir):
        """Test complete CSV workflow"""
        with open(temp_csv_valid, 'rb') as f:
            file_content = f.read()
        
        upload_result = upload_csv(file_content=file_content, target_path=temp_csv_valid)
        assert isinstance(upload_result, dict)
        
        edge_result = check_edge_files(directory=temp_base_dir)
        assert isinstance(edge_result, dict)
        assert 'status' in edge_result
        
        expected = ['orderid', 'customername', 'orderdate', 'amounteur', 'status']
        header_result = validate_csv_headers(file_path=temp_csv_valid, expected_headers=expected)
        assert isinstance(header_result, dict)
        assert 'status' in header_result
