"""
Structured Output Validator for catalog/e-commerce chatbots.

Validates structured output like product lists, HTML cards, tables.
Supports two modes:
- HTML: Parse DOM to extract and validate structured data
- Vision: Use GPT-4 Vision to analyze screenshots (see vision.py)
"""

import re
import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class StructuredValidationResult:
    """Result of structured output validation."""
    passed: bool = False
    score: float = 0.0

    # Extraction details
    extracted_items: List[Dict[str, Any]] = field(default_factory=list)
    extracted_count: int = 0
    extraction_method: str = ""

    # Individual checks
    checks: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Errors and warnings
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'passed': self.passed,
            'score': self.score,
            'extracted_count': self.extracted_count,
            'extraction_method': self.extraction_method,
            'extracted_items': self.extracted_items,
            'checks': self.checks,
            'errors': self.errors,
            'warnings': self.warnings,
        }


class StructuredValidator:
    """
    Validator for structured chatbot output.

    Extracts and validates structured data from HTML or text responses.

    Usage:
        validator = StructuredValidator(config)
        result = validator.validate(
            html_response=html,
            text_response=text,
            criteria={
                "mode": "html",
                "min_results": 1,
                "required_fields": ["name", "price"],
                "field_rules": {"price": {"lt": 100}}
            }
        )
    """

    def __init__(self, config: Any = None):
        """
        Initialize validator.

        Args:
            config: EvaluationConfig (optional, for threshold settings)
        """
        self.config = config
        self._bs4_available = None

    def _check_bs4(self) -> bool:
        """Check if BeautifulSoup is available."""
        if self._bs4_available is None:
            try:
                from bs4 import BeautifulSoup
                self._bs4_available = True
            except ImportError:
                self._bs4_available = False
                logger.warning("BeautifulSoup not installed. HTML parsing will use fallback.")
        return self._bs4_available

    def validate(
        self,
        html_response: Optional[str],
        text_response: str,
        screenshot_path: Optional[str] = None,
        criteria: Optional[Dict[str, Any]] = None
    ) -> StructuredValidationResult:
        """
        Validate structured output.

        Args:
            html_response: HTML content of the response
            text_response: Plain text of the response
            screenshot_path: Path to screenshot (for vision mode)
            criteria: Validation criteria from test case

        Returns:
            StructuredValidationResult with validation details
        """
        result = StructuredValidationResult()

        if not criteria:
            result.passed = True
            result.score = 1.0
            return result

        mode = criteria.get("mode", "html")

        if mode == "html":
            return self._validate_html(html_response, text_response, criteria)
        elif mode == "vision":
            # Vision validation is handled by VisionValidator
            result.errors.append("Vision mode requires VisionValidator")
            return result
        elif mode == "text":
            return self._validate_text(text_response, criteria)
        else:
            result.errors.append(f"Unknown validation mode: {mode}")
            return result

    def _validate_html(
        self,
        html: Optional[str],
        text: str,
        criteria: Dict[str, Any]
    ) -> StructuredValidationResult:
        """Validate HTML structured output."""
        result = StructuredValidationResult()

        if not html and not text:
            result.errors.append("No HTML or text response provided")
            return result

        # Extract items from HTML or text
        items, method = self._extract_items(html, text, criteria)
        result.extracted_items = items
        result.extracted_count = len(items)
        result.extraction_method = method

        if not items and (criteria.get("min_results", 0) > 0):
            result.errors.append("No items extracted from response")
            result.score = 0.0
            return result

        # Run validation checks
        checks_passed = 0
        total_checks = 0

        # 1. Count check
        count_check = self._check_count(
            len(items),
            criteria.get("min_results"),
            criteria.get("max_results")
        )
        result.checks["count"] = count_check
        total_checks += 1
        if count_check.get("passed", False):
            checks_passed += 1

        # 2. Required fields check
        if criteria.get("required_fields"):
            fields_check = self._check_required_fields(
                items,
                criteria.get("required_fields", [])
            )
            result.checks["required_fields"] = fields_check
            total_checks += 1
            if fields_check.get("passed", False):
                checks_passed += 1

        # 3. Field rules check
        if criteria.get("field_rules"):
            rules_check = self._check_field_rules(
                items,
                criteria.get("field_rules", {})
            )
            result.checks["field_rules"] = rules_check
            total_checks += 1
            if rules_check.get("passed", False):
                checks_passed += 1

        # Calculate score
        if total_checks > 0:
            result.score = checks_passed / total_checks
        else:
            result.score = 1.0 if items else 0.0

        # Determine pass/fail
        threshold = 0.7
        if self.config and hasattr(self.config, 'structured_threshold'):
            threshold = self.config.structured_threshold

        result.passed = result.score >= threshold

        # Collect errors from failed checks
        for check_name, check_result in result.checks.items():
            if not check_result.get("passed", True):
                msg = check_result.get("message", f"{check_name} failed")
                result.errors.append(msg)

        return result

    def _validate_text(
        self,
        text: str,
        criteria: Dict[str, Any]
    ) -> StructuredValidationResult:
        """Validate text-based structured output."""
        return self._validate_html(None, text, criteria)

    def _extract_items(
        self,
        html: Optional[str],
        text: str,
        criteria: Dict[str, Any]
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Extract structured items from response.

        Priority:
        1. HTML with selector (BeautifulSoup)
        2. HTML table parsing
        3. JSON embedded in HTML
        4. Text parsing with regex
        """
        items = []

        if html and self._check_bs4():
            # Try HTML selector first
            selector = criteria.get("html_selector")
            if selector:
                items = self._extract_with_selector(html, selector, criteria)
                if items:
                    return items, "html_selector"

            # Try table parsing
            items = self._extract_html_table(html)
            if items:
                return items, "html_table"

            # Try JSON in HTML
            items = self._extract_json_from_html(html)
            if items:
                return items, "json_embedded"

        # Fallback to text parsing
        items = self._extract_from_text(text, criteria)
        return items, "text_parsed"

    def _extract_with_selector(
        self,
        html: str,
        selector: str,
        criteria: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Extract items using CSS selector."""
        items = []
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')

            elements = soup.select(selector)
            for el in elements:
                item = self._extract_fields_from_element(el, criteria)
                if item:
                    items.append(item)
        except Exception as e:
            logger.warning(f"Selector extraction failed: {e}")

        return items

    def _extract_fields_from_element(
        self,
        element: Any,
        criteria: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract fields from a single HTML element."""
        item = {}

        # Get all text content
        text = element.get_text(separator=" ", strip=True)
        if text:
            item["_text"] = text

        # Try to extract common fields
        field_selectors = criteria.get("field_selectors", {})

        # Default selectors for common fields
        default_selectors = {
            "name": [".product-name", ".title", "h3", "h4", "[data-name]"],
            "price": [".price", ".product-price", "[data-price]", ".cost"],
            "category": [".category", ".type", "[data-category]"],
            "color": [".color", "[data-color]"],
            "availability": [".availability", ".stock", "[data-stock]"],
        }

        for field_name, selectors in {**default_selectors, **field_selectors}.items():
            if not isinstance(selectors, list):
                selectors = [selectors]

            for sel in selectors:
                try:
                    found = element.select_one(sel)
                    if found:
                        value = found.get_text(strip=True)
                        if value:
                            item[field_name] = value
                            break
                except:
                    pass

        # Extract from data attributes
        for attr in element.attrs:
            if attr.startswith("data-"):
                field_name = attr[5:].replace("-", "_")
                item[field_name] = element[attr]

        # If no specific fields found, try to infer from text
        if len(item) <= 1 and text:
            item = self._infer_fields_from_text(text)

        return item

    def _infer_fields_from_text(self, text: str) -> Dict[str, Any]:
        """Infer fields from plain text."""
        item = {"_text": text}

        # Price pattern (Euro)
        price_match = re.search(r'(\d+[.,]\d{2})\s*[€$]|[€$]\s*(\d+[.,]\d{2})', text)
        if price_match:
            price_str = price_match.group(1) or price_match.group(2)
            try:
                item["price"] = float(price_str.replace(",", "."))
            except:
                item["price"] = price_str

        # Try to extract name (first substantial text before price)
        if price_match:
            name_part = text[:price_match.start()].strip()
            if name_part:
                item["name"] = name_part

        return item

    def _extract_html_table(self, html: str) -> List[Dict[str, Any]]:
        """Extract data from HTML tables."""
        items = []
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')

            tables = soup.find_all('table')
            for table in tables:
                # Get headers
                headers = []
                header_row = table.find('tr')
                if header_row:
                    for th in header_row.find_all(['th', 'td']):
                        headers.append(th.get_text(strip=True).lower())

                if not headers:
                    continue

                # Get data rows
                rows = table.find_all('tr')[1:]  # Skip header
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if cells:
                        item = {}
                        for i, cell in enumerate(cells):
                            if i < len(headers):
                                item[headers[i]] = cell.get_text(strip=True)
                        if item:
                            items.append(item)

                if items:
                    break  # Use first table with data

        except Exception as e:
            logger.warning(f"Table extraction failed: {e}")

        return items

    def _extract_json_from_html(self, html: str) -> List[Dict[str, Any]]:
        """Extract JSON data embedded in HTML."""
        import json
        items = []

        try:
            # Look for JSON in script tags
            json_pattern = r'<script[^>]*type=["\']application/json["\'][^>]*>(.+?)</script>'
            matches = re.findall(json_pattern, html, re.DOTALL | re.IGNORECASE)

            for match in matches:
                try:
                    data = json.loads(match)
                    if isinstance(data, list):
                        items.extend(data)
                    elif isinstance(data, dict):
                        # Look for common list keys
                        for key in ['items', 'products', 'results', 'data']:
                            if key in data and isinstance(data[key], list):
                                items.extend(data[key])
                                break
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            logger.debug(f"JSON extraction failed: {e}")

        return items

    def _extract_from_text(
        self,
        text: str,
        criteria: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Extract items from plain text."""
        items = []

        if not text:
            return items

        # Pattern 1: Bullet list "- Name €price" or "- Name, €price"
        bullet_pattern = r'^[\-\*\•]\s*(.+?)(?:\s+[€$]?\s*(\d+[.,]\d{2})\s*[€$]?)?$'

        for line in text.split('\n'):
            line = line.strip()
            match = re.match(bullet_pattern, line)
            if match:
                item = {"name": match.group(1).strip()}
                if match.group(2):
                    try:
                        item["price"] = float(match.group(2).replace(",", "."))
                    except:
                        item["price"] = match.group(2)
                items.append(item)

        # Pattern 2: Numbered list "1. Name - €price"
        if not items:
            numbered_pattern = r'^\d+\.\s*(.+?)\s*[-:]\s*[€$]?\s*(\d+[.,]\d{2})'
            for line in text.split('\n'):
                match = re.match(numbered_pattern, line.strip())
                if match:
                    item = {"name": match.group(1).strip()}
                    try:
                        item["price"] = float(match.group(2).replace(",", "."))
                    except:
                        item["price"] = match.group(2)
                    items.append(item)

        return items

    def _check_count(
        self,
        count: int,
        min_results: Optional[int],
        max_results: Optional[int]
    ) -> Dict[str, Any]:
        """Validate item count against min/max."""
        check = {
            "passed": True,
            "count": count,
            "message": ""
        }

        if min_results is not None and count < min_results:
            check["passed"] = False
            check["message"] = f"Too few items: {count} < {min_results}"

        if max_results is not None and count > max_results:
            check["passed"] = False
            check["message"] = f"Too many items: {count} > {max_results}"

        return check

    def _check_required_fields(
        self,
        items: List[Dict[str, Any]],
        required_fields: List[str]
    ) -> Dict[str, Any]:
        """Check that required fields exist in items."""
        check = {
            "passed": True,
            "found_fields": set(),
            "missing": [],
            "message": ""
        }

        if not required_fields or not items:
            return check

        for i, item in enumerate(items):
            item_keys = set(k.lower() for k in item.keys())
            check["found_fields"].update(item_keys)

            for field in required_fields:
                if field.lower() not in item_keys:
                    check["missing"].append(f"Item {i}: missing '{field}'")

        check["found_fields"] = list(check["found_fields"])

        if check["missing"]:
            check["passed"] = False
            check["message"] = f"Missing required fields: {len(check['missing'])} issues"

        return check

    def _check_field_rules(
        self,
        items: List[Dict[str, Any]],
        field_rules: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Check field values against rules."""
        check = {
            "passed": True,
            "violations": [],
            "message": ""
        }

        if not field_rules or not items:
            return check

        for i, item in enumerate(items):
            for field, rules in field_rules.items():
                value = item.get(field) or item.get(field.lower())
                if value is None:
                    continue

                # Convert value to number if needed for numeric comparisons
                numeric_value = None
                if isinstance(value, (int, float)):
                    numeric_value = value
                elif isinstance(value, str):
                    # Try to extract number from string
                    num_match = re.search(r'(\d+[.,]?\d*)', value.replace(",", "."))
                    if num_match:
                        try:
                            numeric_value = float(num_match.group(1))
                        except:
                            pass

                # Check rules
                for rule_name, rule_value in rules.items():
                    violation = None

                    if rule_name == "lt" and numeric_value is not None:
                        if numeric_value >= rule_value:
                            violation = f"Item {i}: {field}={numeric_value} >= {rule_value}"

                    elif rule_name == "gt" and numeric_value is not None:
                        if numeric_value <= rule_value:
                            violation = f"Item {i}: {field}={numeric_value} <= {rule_value}"

                    elif rule_name == "lte" and numeric_value is not None:
                        if numeric_value > rule_value:
                            violation = f"Item {i}: {field}={numeric_value} > {rule_value}"

                    elif rule_name == "gte" and numeric_value is not None:
                        if numeric_value < rule_value:
                            violation = f"Item {i}: {field}={numeric_value} < {rule_value}"

                    elif rule_name == "eq":
                        if str(value).lower() != str(rule_value).lower():
                            violation = f"Item {i}: {field}='{value}' != '{rule_value}'"

                    elif rule_name == "contains":
                        if str(rule_value).lower() not in str(value).lower():
                            violation = f"Item {i}: {field}='{value}' does not contain '{rule_value}'"

                    elif rule_name == "not_contains":
                        if str(rule_value).lower() in str(value).lower():
                            violation = f"Item {i}: {field}='{value}' contains forbidden '{rule_value}'"

                    elif rule_name == "regex":
                        if not re.search(rule_value, str(value), re.IGNORECASE):
                            violation = f"Item {i}: {field}='{value}' does not match pattern"

                    if violation:
                        check["violations"].append(violation)

        if check["violations"]:
            check["passed"] = False
            check["message"] = f"Field rule violations: {len(check['violations'])} issues"

        return check
