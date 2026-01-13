"""
Vision Validator for screenshot-based output validation.

Uses GPT-4 Vision to analyze screenshots and extract structured data
when HTML parsing is not possible (rendered widgets, canvas, etc.)
"""

import os
import re
import json
import base64
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

from .structured import StructuredValidationResult

logger = logging.getLogger(__name__)


class VisionValidator:
    """
    Validator using GPT-4 Vision for screenshot analysis.

    Used when:
    - Chatbot renders in canvas/WebGL
    - HTML is not accessible (iframe sandbox)
    - Complex visual layouts

    Usage:
        validator = VisionValidator(config)
        result = validator.validate(
            screenshot_path="/path/to/screenshot.png",
            criteria={
                "mode": "vision",
                "vision_prompt": "Count products and extract name, price",
                "expected_count": {"min": 1, "max": 10}
            }
        )
    """

    DEFAULT_PROMPT = """Analyze this chatbot response screenshot.

Extract all product/item information you can see. For each item, extract:
- name: Product or item name
- price: Price if visible (as a number)
- category: Category or type if visible
- availability: Availability status if visible

Return a JSON object with this structure:
{
    "items": [
        {"name": "...", "price": 0.00, "category": "...", "availability": "..."},
        ...
    ],
    "count": <number of items>,
    "notes": "Any relevant observations about the response"
}

Only include fields that are actually visible. Return valid JSON only."""

    def __init__(self, config: Any = None):
        """
        Initialize vision validator.

        Args:
            config: EvaluationConfig with api_key_env and vision_model
        """
        self.config = config
        self._client = None
        self._initialized = False

    def _init_client(self) -> bool:
        """Initialize OpenAI client lazily."""
        if self._initialized:
            return self._client is not None

        self._initialized = True

        try:
            api_key_env = "OPENAI_API_KEY"
            if self.config and hasattr(self.config, 'api_key_env'):
                api_key_env = self.config.api_key_env

            api_key = os.getenv(api_key_env)
            if not api_key:
                logger.warning(f"API key not found in {api_key_env}")
                return False

            from openai import OpenAI
            self._client = OpenAI(api_key=api_key)
            return True

        except ImportError:
            logger.warning("openai package not installed")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            return False

    def _get_model(self) -> str:
        """Get vision model name."""
        if self.config and hasattr(self.config, 'vision_model'):
            return self.config.vision_model
        return "gpt-4o"

    def validate(
        self,
        screenshot_path: str,
        criteria: Dict[str, Any]
    ) -> StructuredValidationResult:
        """
        Validate screenshot using GPT-4 Vision.

        Args:
            screenshot_path: Path to screenshot image
            criteria: Validation criteria including vision_prompt

        Returns:
            StructuredValidationResult with extracted data
        """
        result = StructuredValidationResult()
        result.extraction_method = "vision"

        if not self._init_client():
            result.errors.append("Vision API client not available")
            return result

        # Load and encode image
        image_data = self._load_image(screenshot_path)
        if not image_data:
            result.errors.append(f"Failed to load image: {screenshot_path}")
            return result

        # Build prompt
        prompt = self._build_prompt(criteria)

        # Call Vision API
        try:
            extracted = self._call_vision_api(image_data, prompt)
            if not extracted:
                result.errors.append("Vision API returned no data")
                return result

            # Store extracted items
            items = extracted.get("items", [])
            result.extracted_items = items
            result.extracted_count = len(items)

            # Validate against criteria
            result = self._validate_extracted(result, extracted, criteria)

        except Exception as e:
            logger.error(f"Vision validation error: {e}")
            result.errors.append(f"Vision API error: {str(e)}")

        return result

    def _load_image(self, path: str) -> Optional[str]:
        """Load image and encode as base64."""
        try:
            image_path = Path(path)
            if not image_path.exists():
                logger.error(f"Image not found: {path}")
                return None

            with open(image_path, "rb") as f:
                image_bytes = f.read()

            return base64.b64encode(image_bytes).decode("utf-8")

        except Exception as e:
            logger.error(f"Failed to load image: {e}")
            return None

    def _build_prompt(self, criteria: Dict[str, Any]) -> str:
        """Build extraction prompt from criteria."""
        # Use custom prompt if provided
        custom_prompt = criteria.get("vision_prompt")
        if custom_prompt:
            # Append JSON format instruction
            return f"""{custom_prompt}

Return your analysis as a valid JSON object with:
- "items": array of extracted items (each with name, price, category, etc.)
- "count": number of items found
- "notes": any observations

Return only valid JSON, no other text."""

        return self.DEFAULT_PROMPT

    def _call_vision_api(
        self,
        image_data: str,
        prompt: str
    ) -> Optional[Dict[str, Any]]:
        """Call GPT-4 Vision API."""
        try:
            # Determine image type from data
            image_url = f"data:image/png;base64,{image_data}"

            response = self._client.chat.completions.create(
                model=self._get_model(),
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": image_url, "detail": "high"}
                            }
                        ]
                    }
                ],
                max_tokens=2000,
                temperature=0.1
            )

            content = response.choices[0].message.content

            # Parse JSON from response
            return self._parse_json_response(content)

        except Exception as e:
            logger.error(f"Vision API call failed: {e}")
            raise

    def _parse_json_response(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse JSON from API response."""
        if not content:
            return None

        # Try direct parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from markdown code block
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find JSON object in text
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        logger.warning(f"Could not parse JSON from response: {content[:200]}...")
        return None

    def _validate_extracted(
        self,
        result: StructuredValidationResult,
        extracted: Dict[str, Any],
        criteria: Dict[str, Any]
    ) -> StructuredValidationResult:
        """Validate extracted data against criteria."""
        checks_passed = 0
        total_checks = 0

        # 1. Count check
        expected_count = criteria.get("expected_count", {})
        if expected_count:
            count = extracted.get("count", len(result.extracted_items))
            count_check = {
                "passed": True,
                "count": count,
                "message": ""
            }

            min_count = expected_count.get("min")
            max_count = expected_count.get("max")

            if min_count is not None and count < min_count:
                count_check["passed"] = False
                count_check["message"] = f"Too few items: {count} < {min_count}"

            if max_count is not None and count > max_count:
                count_check["passed"] = False
                count_check["message"] = f"Too many items: {count} > {max_count}"

            result.checks["count"] = count_check
            total_checks += 1
            if count_check["passed"]:
                checks_passed += 1

        # 2. Required fields check
        required_fields = criteria.get("required_fields", [])
        if required_fields and result.extracted_items:
            fields_check = self._check_fields(result.extracted_items, required_fields)
            result.checks["required_fields"] = fields_check
            total_checks += 1
            if fields_check["passed"]:
                checks_passed += 1

        # 3. Field rules check
        field_rules = criteria.get("field_rules", {})
        if field_rules and result.extracted_items:
            rules_check = self._check_rules(result.extracted_items, field_rules)
            result.checks["field_rules"] = rules_check
            total_checks += 1
            if rules_check["passed"]:
                checks_passed += 1

        # Calculate score
        if total_checks > 0:
            result.score = checks_passed / total_checks
        else:
            result.score = 1.0 if result.extracted_items else 0.0

        # Determine pass/fail
        threshold = 0.7
        if self.config and hasattr(self.config, 'structured_threshold'):
            threshold = self.config.structured_threshold

        result.passed = result.score >= threshold

        # Add notes from vision analysis
        notes = extracted.get("notes")
        if notes:
            result.warnings.append(f"Vision notes: {notes}")

        return result

    def _check_fields(
        self,
        items: List[Dict[str, Any]],
        required_fields: List[str]
    ) -> Dict[str, Any]:
        """Check required fields in extracted items."""
        check = {
            "passed": True,
            "missing": [],
            "message": ""
        }

        for i, item in enumerate(items):
            item_keys = set(k.lower() for k in item.keys() if item[k] is not None)

            for field in required_fields:
                if field.lower() not in item_keys:
                    check["missing"].append(f"Item {i}: missing '{field}'")

        if check["missing"]:
            check["passed"] = False
            check["message"] = f"Missing fields: {len(check['missing'])} issues"

        return check

    def _check_rules(
        self,
        items: List[Dict[str, Any]],
        field_rules: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Check field rules on extracted items."""
        check = {
            "passed": True,
            "violations": [],
            "message": ""
        }

        for i, item in enumerate(items):
            for field, rules in field_rules.items():
                value = item.get(field) or item.get(field.lower())
                if value is None:
                    continue

                # Get numeric value if applicable
                numeric_value = None
                if isinstance(value, (int, float)):
                    numeric_value = value
                elif isinstance(value, str):
                    try:
                        numeric_value = float(re.sub(r'[^\d.]', '', value))
                    except:
                        pass

                # Check each rule
                for rule_name, rule_value in rules.items():
                    violation = None

                    if rule_name == "lt" and numeric_value is not None:
                        if numeric_value >= rule_value:
                            violation = f"Item {i}: {field}={numeric_value} >= {rule_value}"

                    elif rule_name == "gt" and numeric_value is not None:
                        if numeric_value <= rule_value:
                            violation = f"Item {i}: {field}={numeric_value} <= {rule_value}"

                    elif rule_name == "contains":
                        if str(rule_value).lower() not in str(value).lower():
                            violation = f"Item {i}: {field} does not contain '{rule_value}'"

                    if violation:
                        check["violations"].append(violation)

        if check["violations"]:
            check["passed"] = False
            check["message"] = f"Rule violations: {len(check['violations'])} issues"

        return check
