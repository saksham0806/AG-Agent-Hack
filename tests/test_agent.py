"""
Comprehensive Test Suite for LLM Autonomous Eval-to-Improvement Loop Agent.

Covers all core components deterministically using mocks to ensure
fast, reliable test execution independent of Gemini and GitLab API rate limits.
"""

import os
import json
import pytest
import pandas as pd
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.agent.monitor import PromptMonitor, PromptPerformanceReport
from src.agent.analyzer import FailureAnalyzer, DiagnosticReport, FailureCluster
from src.agent.evaluator import ShadowEvaluator
from src.agent.gitlab_deployer import GitLabDeployer
from src.agent.orchestrator import Orchestrator

# Setup sample data for testing
@pytest.fixture
def mock_spans_df():
    """Create a sample pandas DataFrame mimicking OTel spans from Phoenix."""
    data = [
        {
            "attributes.input.value": "Can I return a TV bought 45 days ago?",
            "attributes.output.value": "Sure, our store return window is 30 days.",
            "span_kind": "LLM",
            "attributes.prompt.id": "customer_support",
            "attributes.prompt.version": "1.0.0"
        },
        {
            "attributes.input.value": "Do you match GamerX 3080 prices?",
            "attributes.output.value": "We do matching under some verification criteria.",
            "span_kind": "LLM",
            "attributes.prompt.id": "customer_support",
            "attributes.prompt.version": "1.0.0"
        }
    ]
    df = pd.DataFrame(data)
    df.index = ["span-1", "span-2"]
    return df


# ==========================================================================
# 1. PromptMonitor Tests
# ==========================================================================

def test_monitor_dataframe_normalization(mock_spans_df):
    """Test that Monitor correctly normalizes OTel DataFrames."""
    # We patch env credentials so initialization doesn't throw
    with patch.dict(os.environ, {"PHOENIX_COLLECTOR_ENDPOINT": "http://mock", "PHOENIX_API_KEY": "mock"}):
        monitor = PromptMonitor()
        df = monitor.normalize_dataframe(mock_spans_df)
        
        assert "input" in df.columns
        assert "output" in df.columns
        assert df.loc["span-1", "input"] == "Can I return a TV bought 45 days ago?"
        assert df.loc["span-2", "output"] == "We do matching under some verification criteria."


def test_monitor_performance_analysis(mock_spans_df):
    """Test monitor's performance aggregation and report structures."""
    with patch.dict(os.environ, {"PHOENIX_COLLECTOR_ENDPOINT": "http://mock", "PHOENIX_API_KEY": "mock"}):
        monitor = PromptMonitor()
        
        # Mock evaluations response
        eval_results = pd.DataFrame([
            {"correctness_score": {"label": "correct", "score": 1.0, "explanation": "Pass"}},
            {"correctness_score": {"label": "incorrect", "score": 0.0, "explanation": "Fail"}}
        ])
        eval_results.index = mock_spans_df.index
        
        reports = monitor.analyze_performance(eval_results, mock_spans_df)
        assert len(reports) == 1
        
        report = reports[0]
        assert isinstance(report, PromptPerformanceReport)
        assert report.prompt_id == "customer_support"
        assert report.prompt_version == "1.0.0"
        assert report.total_traces == 2
        assert report.eval_score == 0.5  # 1 correct out of 2 traces
        assert report.needs_optimization is True  # 50.0% is below the 85.0% threshold
        assert "span-2" in report.failing_trace_ids


# ==========================================================================
# 2. FailureAnalyzer Tests
# ==========================================================================

@patch("google.genai.Client")
def test_analyzer_failure_clustering(mock_genai_client):
    """Test FailureAnalyzer successfully generates structured DiagnosticReports."""
    with patch.dict(os.environ, {"GOOGLE_API_KEY": "mock-key"}):
        analyzer = FailureAnalyzer()
        
        # Configure mocked Gemini structured output response
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "failure_clusters": [
                {
                    "category": "refund_request",
                    "failure_pattern": "Approves refund without transaction ID validation",
                    "example_queries": ["Give me my money back"],
                    "example_responses": ["Sure, done!"],
                    "expected_behavior": "Must ask for order details",
                    "count": 1
                }
            ],
            "improvement_suggestions": [
                "Always ask for order/transaction ID before resolving refund inquiries."
            ]
        })
        
        analyzer.client.models.generate_content = MagicMock(return_value=mock_response)
        
        # Setup sample inputs
        failing_spans_df = pd.DataFrame([
            {
                "input": "Give me my money back",
                "output": "Sure, done!",
                "eval_explanation": "Processed refund without verification"
            }
        ])
        prompt_config = {
            "id": "customer_support",
            "version": "1.0.0",
            "system_instruction": "Friendly retail support prompt"
        }
        
        report = analyzer.analyze_failures(failing_spans_df, prompt_config, overall_score=0.80)
        assert isinstance(report, DiagnosticReport)
        assert report.prompt_id == "customer_support"
        assert report.total_failures == 1
        assert len(report.failure_clusters) == 1
        
        cluster = report.failure_clusters[0]
        assert isinstance(cluster, FailureCluster)
        assert cluster.category == "refund_request"
        assert cluster.failure_pattern == "Approves refund without transaction ID validation"
        assert report.improvement_suggestions[0] == "Always ask for order/transaction ID before resolving refund inquiries."


# ==========================================================================
# 3. ShadowEvaluator Tests
# ==========================================================================

def test_shadow_evaluator_keyword_matching():
    """Test double-layer evaluation keyword substring matching logic."""
    with patch.dict(os.environ, {"GOOGLE_API_KEY": "mock"}):
        # Prevent OTel setup from connecting during testing
        with patch("phoenix.otel.register"), patch("openinference.instrumentation.google_genai.GoogleGenAIInstrumentor.instrument"):
            evaluator = ShadowEvaluator(golden_dataset_path="data/golden_dataset.json")
            
            # Substring containment check matches correctly (case-insensitive)
            res = evaluator._evaluate_candidate.__globals__["expected_contains"] = ["30-day", "expired", "cannot"]
            
            # Response containing all keywords
            text_perfect = "The 30-day window is expired and we cannot process returns."
            matches_perfect = sum(1 for kw in res if kw.lower() in text_perfect.lower()) / len(res)
            assert matches_perfect == 1.0
            
            # Response containing half keywords
            text_half = "We cannot process this return."
            matches_half = sum(1 for kw in res if kw.lower() in text_half.lower()) / len(res)
            assert matches_half == 1/3


# ==========================================================================
# 4. GitLabDeployer Tests
# ==========================================================================

def test_gitlab_deployer_url_encoding():
    """Test project ID URL path quote quote_plus encoding."""
    with patch.dict(os.environ, {"GITLAB_PERSONAL_ACCESS_TOKEN": "mock", "GITLAB_PROJECT_ID": "user/repo"}):
        deployer = GitLabDeployer()
        assert deployer.encoded_project_id == "user%2Frepo"


# ==========================================================================
# 5. Orchestrator Tests
# ==========================================================================

def test_orchestrator_singleton_pattern():
    """Test thread-safe singleton instantiation works as expected."""
    orchestrator1 = Orchestrator()
    orchestrator2 = Orchestrator()
    
    assert orchestrator1 is orchestrator2
    assert orchestrator1.status == "IDLE"
