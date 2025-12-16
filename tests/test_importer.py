"""
Unit tests for src/test_importer.py
"""

import pytest
import json
from pathlib import Path

# Add src to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.test_importer import (
    FieldMapper, TestValidator, TestImporter, ConflictResolver,
    ValidationReport, ConflictReport, ImportResult,
    extract_spreadsheet_id
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def fixtures_path():
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def valid_tests_path(fixtures_path):
    return fixtures_path / "valid_tests.json"


@pytest.fixture
def invalid_tests_path(fixtures_path):
    return fixtures_path / "invalid_tests.json"


@pytest.fixture
def csv_tests_path(fixtures_path):
    return fixtures_path / "tests.csv"


@pytest.fixture
def sample_tests():
    return [
        {"id": "TEST_001", "question": "How do I reset my password?", "category": "account"},
        {"id": "TEST_002", "question": "What are your hours?", "category": "info"},
    ]


# =============================================================================
# FieldMapper Tests
# =============================================================================

class TestFieldMapper:
    """Tests for FieldMapper class."""

    def test_default_mappings(self):
        """Test that default mappings work."""
        mapper = FieldMapper()
        row = {"domanda": "Test question?", "categoria": "support"}
        result = mapper.apply(row)

        assert result["question"] == "Test question?"
        assert result["category"] == "support"

    def test_custom_mappings(self):
        """Test custom mappings override defaults."""
        mapper = FieldMapper(custom_mappings={"my_question": "question"})
        row = {"my_question": "Custom question?"}
        result = mapper.apply(row)

        assert result["question"] == "Custom question?"

    def test_expected_topics_from_string(self):
        """Test expected_topics parsed from comma-separated string."""
        mapper = FieldMapper()
        row = {"question": "Test?", "expected_topics": "topic1, topic2, topic3"}
        result = mapper.apply(row)

        assert result["expected_topics"] == ["topic1", "topic2", "topic3"]

    def test_expected_topics_from_list(self):
        """Test expected_topics preserved when already a list."""
        mapper = FieldMapper()
        row = {"question": "Test?", "expected_topics": ["topic1", "topic2"]}
        result = mapper.apply(row)

        assert result["expected_topics"] == ["topic1", "topic2"]

    def test_followup_columns_collected(self):
        """Test multiple followup columns are collected into array."""
        mapper = FieldMapper()
        row = {
            "question": "Main question?",
            "followup1": "First followup",
            "followup2": "Second followup",
            "followup_3": "Third followup"
        }
        result = mapper.apply(row)

        assert "followups" in result
        assert len(result["followups"]) == 3
        assert "First followup" in result["followups"]
        assert "Second followup" in result["followups"]

    def test_detect_mappings(self):
        """Test auto-detection of field mappings."""
        mapper = FieldMapper()
        headers = ["id", "question", "domanda", "unknown_field"]
        detected, unmapped = mapper.detect_mappings(headers)

        assert detected["id"] == "id"
        assert detected["question"] == "question"
        assert detected["domanda"] == "question"
        assert "unknown_field" in unmapped

    def test_empty_values_skipped(self):
        """Test that empty values are not included."""
        mapper = FieldMapper()
        row = {"question": "Test?", "category": "", "expected": None}
        result = mapper.apply(row)

        assert "question" in result
        assert "category" not in result
        assert "expected" not in result


# =============================================================================
# TestValidator Tests
# =============================================================================

class TestTestValidator:
    """Tests for TestValidator class."""

    def test_valid_test(self):
        """Test validation of a valid test case."""
        validator = TestValidator()
        test = {"id": "TEST_001", "question": "Valid question?"}
        is_valid, errors = validator.validate(test)

        assert is_valid is True
        assert len(errors) == 0

    def test_missing_question(self):
        """Test that missing question fails validation."""
        validator = TestValidator()
        test = {"id": "TEST_001", "category": "test"}
        is_valid, errors = validator.validate(test)

        assert is_valid is False
        assert any("question" in e for e in errors)

    def test_invalid_id_format(self):
        """Test that invalid ID format is caught."""
        validator = TestValidator()
        test = {"id": "INVALID@ID!", "question": "Test?"}
        is_valid, errors = validator.validate(test)

        assert is_valid is False
        assert any("id" in e for e in errors)

    def test_invalid_expected_topics_type(self):
        """Test that non-array expected_topics fails."""
        validator = TestValidator()
        test = {"question": "Test?", "expected_topics": "should be array"}
        is_valid, errors = validator.validate(test)

        assert is_valid is False
        assert any("expected_topics" in e for e in errors)

    def test_validate_batch(self):
        """Test batch validation."""
        validator = TestValidator()
        tests = [
            {"question": "Valid 1"},
            {"category": "missing question"},
            {"question": "Valid 2"},
        ]
        report = validator.validate_batch(tests)

        assert report.valid_count == 2
        assert report.error_count == 1
        assert report.total == 3

    def test_auto_generate_id(self):
        """Test that missing ID is auto-generated."""
        validator = TestValidator()
        tests = [{"question": "No ID test"}]
        report = validator.validate_batch(tests)

        assert report.valid_count == 1
        assert report.valid_tests[0]["id"] == "TEST_001"


# =============================================================================
# ConflictResolver Tests
# =============================================================================

class TestConflictResolver:
    """Tests for ConflictResolver class."""

    def test_find_conflicts(self, sample_tests):
        """Test conflict detection."""
        existing = [{"id": "TEST_001", "question": "Old question"}]
        resolver = ConflictResolver(existing)

        new_tests = [
            {"id": "TEST_001", "question": "New question"},
            {"id": "TEST_003", "question": "Brand new"},
        ]

        report = resolver.find_conflicts(new_tests)

        assert len(report.conflicts) == 1
        assert len(report.new_only) == 1
        assert report.new_only[0]["id"] == "TEST_003"

    def test_no_conflicts(self, sample_tests):
        """Test when there are no conflicts."""
        existing = [{"id": "TEST_001", "question": "Existing"}]
        resolver = ConflictResolver(existing)

        new_tests = [
            {"id": "TEST_002", "question": "New test"},
            {"id": "TEST_003", "question": "Another new"},
        ]

        report = resolver.find_conflicts(new_tests)

        assert len(report.conflicts) == 0
        assert len(report.new_only) == 2


# =============================================================================
# TestImporter Tests
# =============================================================================

class TestTestImporter:
    """Tests for TestImporter class."""

    def test_import_from_json(self, valid_tests_path):
        """Test importing from JSON file."""
        importer = TestImporter()
        result = importer.import_from_file(str(valid_tests_path))

        assert result.source_type == "file"
        assert len(result.tests) == 3
        assert result.validation_report.valid_count == 3

    def test_import_from_csv(self, csv_tests_path):
        """Test importing from CSV file."""
        importer = TestImporter()
        result = importer.import_from_file(str(csv_tests_path))

        assert result.source_type == "file"
        assert len(result.tests) == 3
        assert result.tests[0]["category"] == "account"

    def test_import_validates_tests(self, invalid_tests_path):
        """Test that import performs validation."""
        importer = TestImporter()
        result = importer.import_from_file(str(invalid_tests_path))

        # Should have some valid and some invalid
        assert result.validation_report.error_count > 0
        assert result.validation_report.valid_count > 0

    def test_unsupported_format(self, fixtures_path):
        """Test error on unsupported file format."""
        importer = TestImporter()

        with pytest.raises(ValueError, match="non supportato"):
            importer.import_from_file(str(fixtures_path / "test.txt"))


# =============================================================================
# Helper Function Tests
# =============================================================================

class TestHelperFunctions:
    """Tests for helper functions."""

    def test_extract_spreadsheet_id_from_url(self):
        """Test extracting ID from Google Sheets URL."""
        # pragma: allowlist secret
        url = "https://docs.google.com/spreadsheets/d/ABC123xyz789/edit#gid=0"
        result = extract_spreadsheet_id(url)
        assert result == "ABC123xyz789"

    def test_extract_spreadsheet_id_already_id(self):
        """Test that plain ID is returned as-is."""
        sheet_id = "ABC123xyz789"  # pragma: allowlist secret
        result = extract_spreadsheet_id(sheet_id)
        assert result == sheet_id

    def test_extract_spreadsheet_id_with_dashes(self):
        """Test ID with dashes and underscores."""
        sheet_id = "ABC-123_xyz"  # pragma: allowlist secret
        result = extract_spreadsheet_id(sheet_id)
        assert result == sheet_id


# =============================================================================
# Integration Tests
# =============================================================================

class TestImporterIntegration:
    """Integration tests for the complete import flow."""

    def test_full_import_flow(self, valid_tests_path):
        """Test complete import with mapping and validation."""
        mapper = FieldMapper()
        validator = TestValidator()
        importer = TestImporter(mapper=mapper, validator=validator)

        result = importer.import_from_file(str(valid_tests_path))

        assert result.tests is not None
        assert len(result.tests) > 0
        assert all("id" in t for t in result.tests)
        assert all("question" in t for t in result.tests)

    def test_import_with_custom_mapping(self, fixtures_path, tmp_path):
        """Test import with custom field mapping."""
        # Create test file with custom field names
        custom_tests = [
            {"domanda": "Prima domanda?", "categoria": "test"},
            {"domanda": "Seconda domanda?", "categoria": "info"},
        ]
        test_file = tmp_path / "custom_tests.json"
        test_file.write_text(json.dumps(custom_tests))

        importer = TestImporter()
        result = importer.import_from_file(str(test_file))

        assert len(result.tests) == 2
        assert result.tests[0]["question"] == "Prima domanda?"
        assert result.tests[0]["category"] == "test"
