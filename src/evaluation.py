"""
Evaluation Module - Response quality assessment

Handles:
- Semantic similarity matching (expected vs actual answer)
- LLM-as-judge evaluation with custom criteria
- RAG metrics (groundedness, faithfulness, relevance)
- Overall pass/fail determination

Providers:
- OpenAI API (GPT-4o-mini) for cloud/CI
- Ollama for local development (optional fallback)
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class EvaluationConfig:
    """Configuration for evaluation system"""
    enabled: bool = False
    provider: str = "openai"  # openai | ollama
    model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    api_key_env: str = "OPENAI_API_KEY"

    # Thresholds
    semantic_threshold: float = 0.8
    judge_threshold: float = 0.7
    rag_threshold: float = 0.6
    structured_threshold: float = 0.7  # For structured output validation

    # Weights for overall score
    semantic_weight: float = 0.3
    judge_weight: float = 0.4
    rag_weight: float = 0.3
    structured_weight: float = 0.0  # Set > 0 to include in overall

    # Vision model for screenshot analysis
    vision_model: str = "gpt-4o"

    @classmethod
    def from_settings(cls, settings: Dict[str, Any]) -> 'EvaluationConfig':
        """Create config from settings.yaml evaluation section (dict format)"""
        eval_cfg = settings.get('evaluation', {})
        return cls(
            enabled=eval_cfg.get('enabled', False),
            provider=eval_cfg.get('provider', 'openai'),
            model=eval_cfg.get('model', 'gpt-4o-mini'),
            embedding_model=eval_cfg.get('embedding_model', 'text-embedding-3-small'),
            api_key_env=eval_cfg.get('api_key_env', 'OPENAI_API_KEY'),
            semantic_threshold=eval_cfg.get('semantic_threshold', 0.8),
            judge_threshold=eval_cfg.get('judge_threshold', 0.7),
            rag_threshold=eval_cfg.get('rag_threshold', 0.6),
            structured_threshold=eval_cfg.get('structured_threshold', 0.7),
            semantic_weight=eval_cfg.get('semantic_weight', 0.3),
            judge_weight=eval_cfg.get('judge_weight', 0.4),
            rag_weight=eval_cfg.get('rag_weight', 0.3),
            structured_weight=eval_cfg.get('structured_weight', 0.0),
            vision_model=eval_cfg.get('vision_model', 'gpt-4o'),
        )

    @classmethod
    def from_dataclass(cls, eval_settings: Any) -> 'EvaluationConfig':
        """Create config from EvaluationSettings dataclass (from config_loader)"""
        return cls(
            enabled=getattr(eval_settings, 'enabled', False),
            provider=getattr(eval_settings, 'provider', 'openai'),
            model=getattr(eval_settings, 'model', 'gpt-4o-mini'),
            embedding_model=getattr(eval_settings, 'embedding_model', 'text-embedding-3-small'),
            api_key_env=getattr(eval_settings, 'api_key_env', 'OPENAI_API_KEY'),
            semantic_threshold=getattr(eval_settings, 'semantic_threshold', 0.8),
            judge_threshold=getattr(eval_settings, 'judge_threshold', 0.7),
            rag_threshold=getattr(eval_settings, 'rag_threshold', 0.6),
            structured_threshold=getattr(eval_settings, 'structured_threshold', 0.7),
            semantic_weight=getattr(eval_settings, 'semantic_weight', 0.3),
            judge_weight=getattr(eval_settings, 'judge_weight', 0.4),
            rag_weight=getattr(eval_settings, 'rag_weight', 0.3),
            structured_weight=getattr(eval_settings, 'structured_weight', 0.0),
            vision_model=getattr(eval_settings, 'vision_model', 'gpt-4o'),
        )


@dataclass
class EvaluationResult:
    """Complete evaluation result for a test response"""

    # Semantic similarity (expected_answer vs actual)
    semantic_score: Optional[float] = None  # 0-1
    semantic_match: Optional[bool] = None

    # LLM-as-judge scores
    judge_score: Optional[float] = None  # 0-1
    judge_reasoning: Optional[str] = None
    judge_criteria: Dict[str, float] = field(default_factory=dict)

    # RAG metrics (RAGAS)
    groundedness: Optional[float] = None  # 0-1
    faithfulness: Optional[float] = None  # 0-1
    relevance: Optional[float] = None  # 0-1
    context_precision: Optional[float] = None  # 0-1

    # Structured output validation
    structured_score: Optional[float] = None  # 0-1
    structured_details: Dict[str, Any] = field(default_factory=dict)
    extracted_items: List[Dict[str, Any]] = field(default_factory=list)
    extraction_method: str = ""

    # Overall
    overall_score: Optional[float] = None  # 0-1
    passed: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'semantic_score': self.semantic_score,
            'semantic_match': self.semantic_match,
            'judge_score': self.judge_score,
            'judge_reasoning': self.judge_reasoning,
            'judge_criteria': self.judge_criteria,
            'groundedness': self.groundedness,
            'faithfulness': self.faithfulness,
            'relevance': self.relevance,
            'context_precision': self.context_precision,
            'structured_score': self.structured_score,
            'structured_details': self.structured_details,
            'extracted_items': self.extracted_items,
            'extraction_method': self.extraction_method,
            'overall_score': self.overall_score,
            'passed': self.passed,
            'error': self.error,
        }

    def summary(self) -> str:
        """Human-readable summary"""
        parts = []
        if self.semantic_score is not None:
            parts.append(f"Semantic: {self.semantic_score:.2f}")
        if self.judge_score is not None:
            parts.append(f"Judge: {self.judge_score:.2f}")
        if self.groundedness is not None:
            parts.append(f"Ground: {self.groundedness:.2f}")
        if self.faithfulness is not None:
            parts.append(f"Faith: {self.faithfulness:.2f}")
        if self.relevance is not None:
            parts.append(f"Relev: {self.relevance:.2f}")
        if self.overall_score is not None:
            parts.append(f"Overall: {self.overall_score:.2f}")
        return " | ".join(parts) if parts else "No evaluation"


class SemanticMatcher:
    """
    Semantic similarity using embeddings.

    Uses OpenAI embeddings by default, with optional Ollama fallback.
    """

    def __init__(self, config: EvaluationConfig):
        self.config = config
        self._client = None
        self._initialized = False

    def _init_client(self) -> bool:
        """Initialize OpenAI client lazily"""
        if self._initialized:
            return self._client is not None

        self._initialized = True

        try:
            api_key = os.getenv(self.config.api_key_env)
            if not api_key:
                logger.warning(f"API key not found in {self.config.api_key_env}")
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

    def get_embedding(self, text: str) -> Optional[List[float]]:
        """Get embedding vector for text"""
        if not self._init_client():
            return None

        try:
            response = self._client.embeddings.create(
                model=self.config.embedding_model,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Embedding error: {e}")
            return None

    def similarity(self, text1: str, text2: str) -> Optional[float]:
        """
        Calculate cosine similarity between two texts.

        Returns:
            Similarity score 0-1, or None on error
        """
        emb1 = self.get_embedding(text1)
        emb2 = self.get_embedding(text2)

        if emb1 is None or emb2 is None:
            return None

        # Cosine similarity
        import math
        dot_product = sum(a * b for a, b in zip(emb1, emb2))
        norm1 = math.sqrt(sum(a * a for a in emb1))
        norm2 = math.sqrt(sum(b * b for b in emb2))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)


class LLMJudge:
    """
    LLM-as-judge for qualitative evaluation.

    Uses structured prompts to evaluate responses on multiple criteria.
    """

    DEFAULT_CRITERIA = {
        "completeness": "Does the response fully address all aspects of the question?",
        "accuracy": "Are the facts and information in the response correct?",
        "clarity": "Is the response clear, well-structured, and easy to understand?",
        "relevance": "Is the response directly relevant to the question asked?",
        "tone": "Is the tone appropriate for a customer service chatbot?",
    }

    def __init__(self, config: EvaluationConfig):
        self.config = config
        self._client = None
        self._initialized = False

    def _init_client(self) -> bool:
        """Initialize OpenAI client lazily"""
        if self._initialized:
            return self._client is not None

        self._initialized = True

        try:
            api_key = os.getenv(self.config.api_key_env)
            if not api_key:
                logger.warning(f"API key not found in {self.config.api_key_env}")
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

    def judge(
        self,
        question: str,
        response: str,
        expected: Optional[str] = None,
        criteria: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Evaluate response quality using LLM.

        Args:
            question: Original user question
            response: Chatbot response to evaluate
            expected: Expected behavior description (optional)
            criteria: Custom evaluation criteria (optional)

        Returns:
            {
                "scores": {"completeness": 0.9, "accuracy": 0.8, ...},
                "overall": 0.85,
                "reasoning": "The response is...",
                "passed": True
            }
        """
        if not self._init_client():
            return {"error": "LLM client not available"}

        criteria = criteria or self.DEFAULT_CRITERIA

        # Build evaluation prompt
        prompt = self._build_judge_prompt(question, response, expected, criteria)

        try:
            completion = self._client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": "You are an expert evaluator of chatbot responses. Evaluate responses objectively and provide structured JSON output."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=1000
            )

            result_text = completion.choices[0].message.content
            result = json.loads(result_text)

            # Calculate overall score from criteria
            scores = result.get("scores", {})
            if scores:
                overall = sum(scores.values()) / len(scores)
                result["overall"] = overall
                result["passed"] = overall >= self.config.judge_threshold

            return result

        except Exception as e:
            logger.error(f"Judge evaluation error: {e}")
            return {"error": str(e)}

    def _build_judge_prompt(
        self,
        question: str,
        response: str,
        expected: Optional[str],
        criteria: Dict[str, str]
    ) -> str:
        """Build the evaluation prompt"""
        criteria_text = "\n".join([
            f"- {name}: {desc}" for name, desc in criteria.items()
        ])

        expected_text = f"\n\nExpected behavior: {expected}" if expected else ""

        return f"""Evaluate the following chatbot response.

Question: {question}

Response: {response}{expected_text}

Evaluate the response on these criteria (score each 0.0 to 1.0):
{criteria_text}

Respond with JSON in this exact format:
{{
    "scores": {{
        "completeness": 0.0,
        "accuracy": 0.0,
        "clarity": 0.0,
        "relevance": 0.0,
        "tone": 0.0
    }},
    "reasoning": "Brief explanation of the evaluation"
}}"""


class RAGEvaluator:
    """
    RAG-specific metrics using RAGAS library.

    Measures:
    - Groundedness: Is the answer grounded in the provided context?
    - Faithfulness: Does the answer accurately represent the context?
    - Relevance: Is the answer relevant to the question?
    - Context Precision: How precise is the context retrieval?
    """

    def __init__(self, config: EvaluationConfig):
        self.config = config
        self._ragas_available = None

    def _check_ragas(self) -> bool:
        """Check if RAGAS is available"""
        if self._ragas_available is not None:
            return self._ragas_available

        try:
            import ragas
            self._ragas_available = True
        except ImportError:
            logger.warning("ragas package not installed. RAG metrics disabled.")
            self._ragas_available = False

        return self._ragas_available

    def evaluate(
        self,
        question: str,
        answer: str,
        contexts: List[str],
        ground_truth: Optional[str] = None
    ) -> Dict[str, float]:
        """
        Evaluate RAG response quality.

        Args:
            question: User question
            answer: Generated answer
            contexts: Retrieved context documents
            ground_truth: Expected answer (optional)

        Returns:
            Dictionary with metric scores
        """
        if not self._check_ragas():
            return self._fallback_evaluation(question, answer, contexts)

        try:
            # Ensure API key is set BEFORE importing RAGAS
            api_key = os.getenv(self.config.api_key_env)
            if not api_key:
                # Try loading from .env
                from dotenv import load_dotenv
                load_dotenv()
                api_key = os.getenv(self.config.api_key_env)

            if not api_key:
                logger.warning(f"No API key found for RAGAS, using fallback")
                return self._fallback_evaluation(question, answer, contexts)

            # Set in environment for RAGAS
            os.environ["OPENAI_API_KEY"] = api_key

            from ragas import evaluate
            from ragas.metrics import (
                faithfulness,
                answer_relevancy,
            )
            from datasets import Dataset

            # Prepare dataset for RAGAS
            data = {
                "question": [question],
                "answer": [answer],
                "contexts": [contexts],
            }
            if ground_truth:
                data["reference"] = [ground_truth]  # RAGAS usa 'reference' per ground truth

            dataset = Dataset.from_dict(data)

            # Select metrics (only faithfulness and answer_relevancy - no ground truth needed)
            metrics = [faithfulness, answer_relevancy]

            # Evaluate
            result = evaluate(dataset, metrics=metrics)

            # Gestisci sia dict (vecchia API) che EvaluationResult object (nuova API)
            if hasattr(result, 'get') and callable(getattr(result, 'get')):
                # Vecchia API RAGAS (<0.1.0): ritorna dict
                faithfulness_score = result.get("faithfulness", 0.0)
                relevance_score = result.get("answer_relevancy", 0.0)
            else:
                # Nuova API RAGAS (>=0.1.0): ritorna EvaluationResult object
                # Prova ad accedere come attributo o tramite scores dict
                if hasattr(result, 'scores'):
                    # RAGAS 0.1.x: result.scores è un dict
                    scores = result.scores if isinstance(result.scores, dict) else {}
                    faithfulness_score = scores.get("faithfulness", 0.0)
                    relevance_score = scores.get("answer_relevancy", 0.0)
                elif hasattr(result, '__getitem__'):
                    # Prova accesso dict-like
                    try:
                        faithfulness_score = result["faithfulness"] if "faithfulness" in result else 0.0
                        relevance_score = result["answer_relevancy"] if "answer_relevancy" in result else 0.0
                    except (KeyError, TypeError):
                        faithfulness_score = 0.0
                        relevance_score = 0.0
                else:
                    # Fallback: prova getattr
                    faithfulness_score = getattr(result, "faithfulness", 0.0)
                    relevance_score = getattr(result, "answer_relevancy", 0.0)

            # Converti a float se necessario (RAGAS può ritornare numpy types)
            try:
                faithfulness_score = float(faithfulness_score) if faithfulness_score is not None else 0.0
                relevance_score = float(relevance_score) if relevance_score is not None else 0.0
            except (ValueError, TypeError):
                faithfulness_score = 0.0
                relevance_score = 0.0

            return {
                "faithfulness": faithfulness_score,
                "relevance": relevance_score,
                "context_precision": 0.0,  # Requires ground truth, skip
                "groundedness": faithfulness_score,  # Alias
            }

        except Exception as e:
            logger.error(f"RAGAS evaluation error: {e}")
            return self._fallback_evaluation(question, answer, contexts)

    def _fallback_evaluation(
        self,
        question: str,
        answer: str,
        contexts: List[str]
    ) -> Dict[str, float]:
        """
        Simple fallback when RAGAS is not available.
        Uses basic heuristics.
        """
        if not contexts:
            return {
                "faithfulness": 0.0,
                "relevance": 0.0,
                "context_precision": 0.0,
                "groundedness": 0.0,
            }

        # Simple word overlap heuristic
        context_text = " ".join(contexts).lower()
        answer_words = set(answer.lower().split())
        context_words = set(context_text.split())
        question_words = set(question.lower().split())

        # Remove common words
        stopwords = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                     "being", "have", "has", "had", "do", "does", "did", "will",
                     "would", "could", "should", "may", "might", "must", "shall",
                     "can", "need", "dare", "ought", "used", "to", "of", "in",
                     "for", "on", "with", "at", "by", "from", "as", "into",
                     "through", "during", "before", "after", "above", "below",
                     "between", "under", "again", "further", "then", "once",
                     "here", "there", "when", "where", "why", "how", "all",
                     "each", "few", "more", "most", "other", "some", "such",
                     "no", "nor", "not", "only", "own", "same", "so", "than",
                     "too", "very", "just", "and", "but", "if", "or", "because",
                     "until", "while", "this", "that", "these", "those", "i",
                     "you", "he", "she", "it", "we", "they", "what", "which",
                     "who", "whom", "whose", "il", "lo", "la", "i", "gli", "le",
                     "un", "uno", "una", "di", "a", "da", "in", "con", "su",
                     "per", "tra", "fra", "che", "e", "o", "ma", "se", "come",
                     "quando", "dove", "perché", "questo", "quello", "questi",
                     "quelli", "sono", "è", "essere", "avere", "fare", "dire"}

        answer_words -= stopwords
        context_words -= stopwords
        question_words -= stopwords

        if not answer_words:
            return {
                "faithfulness": 0.5,
                "relevance": 0.5,
                "context_precision": 0.5,
                "groundedness": 0.5,
            }

        # Groundedness: how much of answer is in context
        overlap_with_context = len(answer_words & context_words) / len(answer_words)

        # Relevance: how much of answer relates to question
        overlap_with_question = len(answer_words & question_words) / len(answer_words)

        return {
            "faithfulness": min(1.0, overlap_with_context),
            "relevance": min(1.0, overlap_with_question * 2),  # Scale up
            "context_precision": min(1.0, overlap_with_context),
            "groundedness": min(1.0, overlap_with_context),
        }


class Evaluator:
    """
    Main evaluator orchestrating all evaluation components.

    Usage:
        config = EvaluationConfig.from_settings(settings)
        evaluator = Evaluator(config, project_path)

        result = await evaluator.evaluate(
            question="What products do you have?",
            response="We have products A, B, and C.",
            expected_answer="We offer products A, B, C, and D.",
            rag_context_file="knowledge/products.md",
            criteria={"accuracy": "Are product names correct?"}
        )

        if result.passed:
            print("Test passed!")
        else:
            print(f"Failed: {result.summary()}")
    """

    def __init__(self, config: EvaluationConfig, project_path: Optional[Path] = None):
        self.config = config
        self.project_path = project_path

        # Initialize components
        self.semantic_matcher = SemanticMatcher(config)
        self.judge = LLMJudge(config)
        self.rag_evaluator = RAGEvaluator(config)

        # Structured output validators
        self.structured_validator = None
        self.vision_validator = None
        try:
            from .validators import StructuredValidator, VisionValidator
            self.structured_validator = StructuredValidator(config)
            self.vision_validator = VisionValidator(config)
        except ImportError:
            logger.debug("Structured validators not available")

    def load_rag_context(self, context_file: str) -> Optional[str]:
        """Load RAG context from file"""
        if not self.project_path or not context_file:
            return None

        context_path = self.project_path / context_file
        if not context_path.exists():
            logger.warning(f"RAG context file not found: {context_path}")
            return None

        try:
            return context_path.read_text(encoding='utf-8')
        except Exception as e:
            logger.error(f"Error reading context file: {e}")
            return None

    def evaluate(
        self,
        question: str,
        response: str,
        expected_answer: Optional[str] = None,
        expected_behavior: Optional[str] = None,
        rag_context_file: Optional[str] = None,
        rag_context: Optional[str] = None,
        criteria: Optional[Dict[str, str]] = None,
        output_validation: Optional[Dict[str, Any]] = None,
        html_response: Optional[str] = None,
        screenshot_path: Optional[str] = None
    ) -> EvaluationResult:
        """
        Perform complete evaluation of a chatbot response.

        Args:
            question: Original user question
            response: Chatbot response to evaluate
            expected_answer: Expected answer for semantic matching
            expected_behavior: Qualitative expected behavior description
            rag_context_file: Path to RAG context file (relative to project)
            rag_context: Direct RAG context string (alternative to file)
            criteria: Custom LLM-as-judge criteria
            output_validation: Structured output validation criteria
            html_response: HTML content for structured validation
            screenshot_path: Screenshot path for vision validation

        Returns:
            EvaluationResult with all scores and pass/fail determination
        """
        if not self.config.enabled:
            return EvaluationResult(passed=True, error="Evaluation disabled")

        result = EvaluationResult()
        scores_for_overall = []
        weights = []

        try:
            # 1. Semantic similarity (if expected_answer provided)
            if expected_answer:
                semantic_score = self.semantic_matcher.similarity(
                    expected_answer, response
                )
                if semantic_score is not None:
                    result.semantic_score = semantic_score
                    result.semantic_match = semantic_score >= self.config.semantic_threshold
                    scores_for_overall.append(semantic_score)
                    weights.append(self.config.semantic_weight)

            # 2. LLM-as-judge
            judge_result = self.judge.judge(
                question=question,
                response=response,
                expected=expected_behavior,
                criteria=criteria
            )

            if "error" not in judge_result:
                result.judge_score = judge_result.get("overall")
                result.judge_reasoning = judge_result.get("reasoning")
                result.judge_criteria = judge_result.get("scores", {})
                if result.judge_score is not None:
                    scores_for_overall.append(result.judge_score)
                    weights.append(self.config.judge_weight)

            # 3. RAG metrics (if context provided)
            context = rag_context
            if not context and rag_context_file:
                context = self.load_rag_context(rag_context_file)

            if context:
                rag_result = self.rag_evaluator.evaluate(
                    question=question,
                    answer=response,
                    contexts=[context],
                    ground_truth=expected_answer
                )

                result.groundedness = rag_result.get("groundedness")
                result.faithfulness = rag_result.get("faithfulness")
                result.relevance = rag_result.get("relevance")
                result.context_precision = rag_result.get("context_precision")

                # Average RAG metrics for overall
                rag_scores = [v for v in rag_result.values() if v is not None]
                if rag_scores:
                    rag_avg = sum(rag_scores) / len(rag_scores)
                    scores_for_overall.append(rag_avg)
                    weights.append(self.config.rag_weight)

            # 4. Structured output validation (if criteria provided)
            if output_validation and (self.structured_validator or self.vision_validator):
                mode = output_validation.get("mode", "html")

                if mode == "vision" and self.vision_validator and screenshot_path:
                    struct_result = self.vision_validator.validate(
                        screenshot_path=screenshot_path,
                        criteria=output_validation
                    )
                elif self.structured_validator:
                    struct_result = self.structured_validator.validate(
                        html_response=html_response,
                        text_response=response,
                        screenshot_path=screenshot_path,
                        criteria=output_validation
                    )
                else:
                    struct_result = None

                if struct_result:
                    result.structured_score = struct_result.score
                    result.structured_details = struct_result.to_dict()
                    result.extracted_items = struct_result.extracted_items
                    result.extraction_method = struct_result.extraction_method

                    if struct_result.score is not None and self.config.structured_weight > 0:
                        scores_for_overall.append(struct_result.score)
                        weights.append(self.config.structured_weight)

            # 5. Calculate overall score
            if scores_for_overall:
                total_weight = sum(weights)
                if total_weight > 0:
                    result.overall_score = sum(
                        s * w for s, w in zip(scores_for_overall, weights)
                    ) / total_weight
                else:
                    result.overall_score = sum(scores_for_overall) / len(scores_for_overall)

                # Determine pass/fail
                result.passed = self._determine_pass(result)
            else:
                # No evaluation possible, default to pass
                result.passed = True
                result.error = "No evaluation metrics available"

        except Exception as e:
            logger.error(f"Evaluation error: {e}")
            result.error = str(e)
            result.passed = False

        return result

    def _determine_pass(self, result: EvaluationResult) -> bool:
        """
        Determine if the test passes based on evaluation results.

        Logic:
        - If semantic_match is False, fail
        - If judge_score < threshold, fail
        - If overall_score < min(thresholds), fail
        - Otherwise pass
        """
        # Semantic match is a hard requirement if provided
        if result.semantic_match is False:
            return False

        # Check individual thresholds
        if result.judge_score is not None:
            if result.judge_score < self.config.judge_threshold:
                return False

        # Check structured validation threshold
        if result.structured_score is not None:
            if result.structured_score < self.config.structured_threshold:
                return False

        # Check overall score against minimum threshold
        min_threshold = min(
            self.config.semantic_threshold,
            self.config.judge_threshold,
            self.config.rag_threshold,
            self.config.structured_threshold
        )

        if result.overall_score is not None:
            return result.overall_score >= min_threshold

        return True


def create_evaluator(settings: Dict[str, Any], project_path: Optional[Path] = None) -> Evaluator:
    """
    Factory function to create an Evaluator from settings dict.

    Args:
        settings: Global settings dictionary (from settings.yaml)
        project_path: Path to project directory (for loading RAG context files)

    Returns:
        Configured Evaluator instance
    """
    config = EvaluationConfig.from_settings(settings)
    return Evaluator(config, project_path)


def create_evaluator_from_settings(eval_settings: Any, project_path: Optional[Path] = None) -> Evaluator:
    """
    Factory function to create an Evaluator from EvaluationSettings dataclass.

    Args:
        eval_settings: EvaluationSettings dataclass (from config_loader.GlobalSettings.evaluation)
        project_path: Path to project directory (for loading RAG context files)

    Returns:
        Configured Evaluator instance
    """
    config = EvaluationConfig.from_dataclass(eval_settings)
    return Evaluator(config, project_path)
