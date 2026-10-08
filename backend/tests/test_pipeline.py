from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.llm import UNKNOWN_FALLBACK, UNKNOWN_FALLBACK_EN, generate_guidance, validate_answer
from app.main import app

CHUNKS = [
    {
        "text": "Workers can submit wage complaints through SAMADHAN.",
        "title": "SAMADHAN worker grievance portal",
        "source_url": "https://samadhan.labour.gov.in/",
        "topic": "unpaid_wages",
    }
]

ANSWER = {
    "crisis_type": "unpaid_wages",
    "urgency": "high",
    "summary_hi": "आपका वेतन बाकी है।",
    "steps_hi": ["वेतन की पर्ची रखें।", "तारीखें लिखें।", "SAMADHAN देखें।"],
    "document_issues": [],
    "sources": [
        {
            "name": "SAMADHAN worker grievance portal",
            "url": "https://samadhan.labour.gov.in/",
        }
    ],
    "unknown": False,
}

ANSWER_EN = {
    "crisis_type": "unpaid_wages",
    "urgency": "high",
    "summary_hi": "Your wages are overdue.",
    "steps_hi": ["Keep your payslip.", "List the unpaid months.", "Check SAMADHAN for complaint options."],
    "document_issues": [],
    "sources": ANSWER["sources"],
    "unknown": False,
}


class AnswerValidationTests(unittest.TestCase):
    def test_accepts_only_retrieved_source_pairs(self) -> None:
        answer = {**ANSWER, "sources": ANSWER["sources"] + [{
            "name": "Fake source",
            "url": "https://not-government.example/",
        }]}

        validated = validate_answer(answer, CHUNKS)

        self.assertEqual(validated["sources"], ANSWER["sources"])
        self.assertFalse(validated["unknown"])

    def test_unmatched_source_returns_unknown_fallback(self) -> None:
        answer = {**ANSWER, "sources": [{"name": "SAMADHAN", "url": "https://samadhan.labour.gov.in/extra"}]}

        validated = validate_answer(answer, CHUNKS)

        self.assertTrue(validated["unknown"])
        self.assertEqual(validated["sources"], UNKNOWN_FALLBACK["sources"])

    def test_empty_retrieval_returns_unknown_fallback(self) -> None:
        validated = validate_answer(ANSWER, [])

        self.assertTrue(validated["unknown"])
        self.assertEqual(validated["crisis_type"], "other")

    def test_empty_retrieval_fallback_matches_selected_language(self) -> None:
        answer = validate_answer(ANSWER, [], language="en")

        self.assertEqual(answer["summary_hi"], UNKNOWN_FALLBACK_EN["summary_hi"])

    def test_prompt_declares_worker_topic_scope(self) -> None:
        from app.prompts import system_prompt_for

        prompt = system_prompt_for("en")
        self.assertIn("Do not answer unrelated questions", prompt)
        self.assertIn("worker and labour matters", prompt)

    def test_hindi_model_text_is_rejected_in_english_mode(self) -> None:
        answer = validate_answer(ANSWER, CHUNKS, language="en")

        self.assertTrue(answer["unknown"])
        self.assertEqual(answer["summary_hi"], UNKNOWN_FALLBACK_EN["summary_hi"])

    def test_english_model_text_is_preserved_in_english_mode(self) -> None:
        answer = validate_answer(ANSWER_EN, CHUNKS, language="en")

        self.assertFalse(answer["unknown"])
        self.assertEqual(answer["summary_hi"], ANSWER_EN["summary_hi"])

    def test_document_issues_are_returned_only_when_a_document_was_supplied(self) -> None:
        answer_with_findings = {
            **ANSWER_EN,
            "document_issues": [{
                "issue": "The payslip does not show a payment date.",
                "action": "Ask payroll to confirm the date and check it against your bank record.",
            }],
        }

        with_document = validate_answer(answer_with_findings, CHUNKS, "en", document_provided=True)
        without_document = validate_answer(answer_with_findings, CHUNKS, "en")

        self.assertEqual(len(with_document["document_issues"]), 1)
        self.assertEqual(without_document["document_issues"], [])

    def test_document_findings_survive_unknown_retrieval_fallback(self) -> None:
        answer_with_findings = {
            **ANSWER_EN,
            "unknown": True,
            "document_issues": [{"issue": "Payment date is missing.", "action": "Ask payroll to confirm it."}],
        }

        result = validate_answer(answer_with_findings, [], "en", document_provided=True)

        self.assertTrue(result["unknown"])
        self.assertEqual(result["document_issues"], answer_with_findings["document_issues"])

    def test_malformed_schema_returns_unknown_fallback(self) -> None:
        validated = validate_answer({**ANSWER, "steps_hi": ["एक कदम"]}, CHUNKS)

        self.assertTrue(validated["unknown"])
        self.assertEqual(validated["steps_hi"], UNKNOWN_FALLBACK["steps_hi"])

    def test_critical_urgency_is_restricted_to_immediate_danger_types(self) -> None:
        validated = validate_answer({**ANSWER, "urgency": "critical"}, CHUNKS)

        self.assertEqual(validated["urgency"], "high")


class GeminiCallTests(unittest.TestCase):
    def test_valid_response_uses_one_generate_call_with_image(self) -> None:
        client = MagicMock()
        answer = {
            **ANSWER_EN,
            "document_issues": [{"issue": "The date is unreadable.", "action": "Ask the issuer for a clear copy."}],
        }
        client.models.generate_content.return_value = SimpleNamespace(text=json.dumps(answer))

        with patch("app.llm._client", return_value=client):
            answer = generate_guidance(
                "Review this payslip", "", CHUNKS, images=[(b"image", "image/png")], language="en", document_provided=True
            )

        self.assertEqual(answer["crisis_type"], "unpaid_wages")
        client.models.generate_content.assert_called_once()
        contents = client.models.generate_content.call_args.kwargs["contents"]
        self.assertEqual(len(contents), 2)
        config = client.models.generate_content.call_args.kwargs["config"]
        self.assertIn("simple English", config.system_instruction)
        contents = client.models.generate_content.call_args.kwargs["contents"]
        self.assertIn("English only", contents[0])
        self.assertEqual(len(answer["document_issues"]), 1)

    def test_invalid_json_retries_once(self) -> None:
        client = MagicMock()
        client.models.generate_content.side_effect = [
            SimpleNamespace(text="not json"),
            SimpleNamespace(text=json.dumps(ANSWER)),
        ]

        with patch("app.llm._client", return_value=client):
            answer = generate_guidance("समस्या", "", CHUNKS)

        self.assertEqual(answer["crisis_type"], "unpaid_wages")
        self.assertEqual(client.models.generate_content.call_count, 2)


class ApiPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.upload_dir = root / "uploads"
        self.upload_dir.mkdir()
        self.patches = ExitStack()
        self.patches.enter_context(patch("app.db.SQLITE_PATH", root / "cases.db"))
        self.patches.enter_context(patch("app.main.UPLOADS_DIR", self.upload_dir))
        self.patches.enter_context(patch("app.main.GEMINI_API_KEY", "test-key"))
        self.query_mock = self.patches.enter_context(
            patch("app.main.query_chunks", return_value=CHUNKS)
        )
        self.guidance_mock = self.patches.enter_context(
            patch("app.main.generate_guidance", return_value=ANSWER)
        )
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        self.patches.close()
        self.temp_dir.cleanup()

    def test_health(self) -> None:
        response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

    def test_text_only_case_is_saved_and_returned(self) -> None:
        response = self.client.post("/api/ask", data={"text": "तीन महीने से वेतन नहीं मिला"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["crisis_type"], "unpaid_wages")
        self.assertEqual(self.client.get(f"/api/cases/{body['id']}").json()["transcript"], body["transcript"])
        self.assertEqual(len(self.client.get("/api/cases").json()["cases"]), 1)
        self.query_mock.assert_called_once()
        self.guidance_mock.assert_called_once()

    def test_selected_english_language_reaches_guidance(self) -> None:
        response = self.client.post(
            "/api/ask",
            data={"text": "I have not been paid", "language": "en"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.guidance_mock.call_args.kwargs["language"], "en")

    def test_ask_defaults_to_english(self) -> None:
        response = self.client.post("/api/ask", data={"text": "I need help"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["language"], "en")
        self.assertEqual(self.guidance_mock.call_args.kwargs["language"], "en")

    def test_case_language_is_returned_and_saved(self) -> None:
        response = self.client.post(
            "/api/ask",
            data={"text": "I have not been paid", "language": "en"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["language"], "en")
        saved = self.client.get(f"/api/cases/{response.json()['id']}?language=en")
        self.assertEqual(saved.json()["language"], "en")

    def test_missing_chroma_returns_localized_setup_error(self) -> None:
        with patch("app.main.query_chunks", side_effect=ModuleNotFoundError(name="chromadb")):
            response = self.client.post(
                "/api/ask",
                data={"text": "मेरा वेतन नहीं मिला", "language": "hi"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("ज्ञान आधार तैयार नहीं है", response.json()["detail"])
        self.guidance_mock.assert_not_called()

    def test_missing_chroma_setup_error_is_english(self) -> None:
        with patch("app.main.query_chunks", side_effect=ModuleNotFoundError(name="chromadb")):
            response = self.client.post(
                "/api/ask",
                data={"text": "My wages were not paid", "language": "en"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("knowledge base is not installed", response.json()["detail"])

    def test_empty_question_returns_400(self) -> None:
        response = self.client.post("/api/ask", data={"text": "  "})

        self.assertEqual(response.status_code, 400)
        self.guidance_mock.assert_not_called()

    def test_empty_question_error_is_english(self) -> None:
        response = self.client.post(
            "/api/ask",
            data={"text": "  ", "language": "en"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Speech or a written message is required.")

    def test_empty_question_fails_before_gemini_key_check(self) -> None:
        with patch("app.main.GEMINI_API_KEY", ""):
            response = self.client.post(
                "/api/ask",
                data={"text": "  ", "language": "hi"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("आवाज़ या लिखा हुआ संदेश", response.json()["detail"])

    def test_missing_gemini_key_fails_before_retrieval(self) -> None:
        with patch("app.main.GEMINI_API_KEY", ""):
            response = self.client.post("/api/ask", data={"text": "वेतन नहीं मिला"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("GEMINI_API_KEY", response.json()["detail"])
        self.query_mock.assert_not_called()
        self.guidance_mock.assert_not_called()

    def test_missing_gemini_key_is_localized_for_english(self) -> None:
        with patch("app.main.GEMINI_API_KEY", ""):
            response = self.client.post(
                "/api/ask",
                data={"text": "I need help", "language": "en"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("GEMINI_API_KEY is missing", response.json()["detail"])

    def test_document_without_question_is_reviewed(self) -> None:
        with patch("app.main._pdf_text", return_value="Employer: Example Ltd\nPayment date: missing"):
            response = self.client.post(
                "/api/ask",
                files={"files": ("payslip.pdf", b"%PDF-fake", "application/pdf")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("uploaded document", self.guidance_mock.call_args.args[0])
        self.assertTrue(self.guidance_mock.call_args.kwargs["document_provided"])

    def test_document_findings_are_saved_with_the_case(self) -> None:
        finding = {"issue": "Payment date is missing.", "action": "Ask payroll to confirm it."}
        self.guidance_mock.return_value = {**ANSWER, "document_issues": [finding]}
        with patch("app.main._pdf_text", return_value="Employer: Example Ltd"):
            response = self.client.post(
                "/api/ask",
                data={"language": "en"},
                files={"files": ("payslip.pdf", b"%PDF-fake", "application/pdf")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["document_issues"], [finding])
        saved = self.client.get(f"/api/cases/{response.json()['id']}?language=en")
        self.assertEqual(saved.json()["document_issues"], [finding])

    def test_unsupported_file_is_rejected_before_saving(self) -> None:
        response = self.client.post(
            "/api/ask",
            data={"text": "मेरी मदद करें"},
            files={"files": ("notice.exe", b"not a document", "application/octet-stream")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(list(self.upload_dir.iterdir()), [])
        self.guidance_mock.assert_not_called()

    def test_oversized_document_is_rejected(self) -> None:
        with patch("app.main.MAX_UPLOAD_BYTES", 4):
            response = self.client.post(
                "/api/ask",
                data={"text": "मेरी मदद करें"},
                files={"files": ("notice.pdf", b"12345", "application/pdf")},
            )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(list(self.upload_dir.iterdir()), [])
        self.guidance_mock.assert_not_called()

    def test_invalid_pdf_returns_readable_error(self) -> None:
        response = self.client.post(
            "/api/ask",
            data={"text": "इस नोटिस को समझें"},
            files={"files": ("notice.pdf", b"not a PDF", "application/pdf")},
        )

        self.assertEqual(response.status_code, 400)
        self.guidance_mock.assert_not_called()

    def test_pdf_text_is_added_to_retrieval_and_saved_case(self) -> None:
        with patch("app.main._pdf_text", return_value="वेतन का नोटिस"):
            response = self.client.post(
                "/api/ask",
                data={"text": "इसे समझें"},
                files={"files": ("notice.pdf", b"%PDF-fake", "application/pdf")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("वेतन का नोटिस", self.query_mock.call_args.args[0])
        self.assertEqual(response.json()["filenames"], ["notice.pdf"])

    def test_image_is_passed_to_the_single_guidance_call(self) -> None:
        response = self.client.post(
            "/api/ask",
            data={"text": "इस फोटो को देखें"},
            files={"files": ("notice.png", b"image-bytes", "image/png")},
        )

        self.assertEqual(response.status_code, 200)
        self.guidance_mock.assert_called_once()
        self.assertEqual(self.guidance_mock.call_args.kwargs["images"], [(b"image-bytes", "image/png")])

    def test_case_not_found_returns_404(self) -> None:
        response = self.client.get("/api/cases/9999")

        self.assertEqual(response.status_code, 404)

    def test_case_not_found_error_is_english_by_default(self) -> None:
        response = self.client.get("/api/cases/9999")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Case not found.")

    def test_case_not_found_error_can_be_hindi(self) -> None:
        response = self.client.get("/api/cases/9999?language=hi")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "केस नहीं मिला।")

    def test_transcribe_reports_missing_groq_key(self) -> None:
        with patch("app.stt.GROQ_API_KEY", ""):
            response = self.client.post(
                "/api/transcribe",
                params={"language": "hi"},
                files={"audio": ("voice.webm", b"audio", "audio/webm")},
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("GROQ_API_KEY", response.json()["detail"])

    def test_transcribe_errors_are_english_by_default(self) -> None:
        with patch("app.main.transcribe_audio", side_effect=RuntimeError("Groq failure")):
            response = self.client.post(
                "/api/transcribe",
                files={"audio": ("voice.webm", b"audio", "audio/webm")},
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Speech recognition failed", response.json()["detail"])

    def test_transcribe_invalid_groq_key_is_actionable_in_english(self) -> None:
        with patch(
            "app.main.transcribe_audio",
            side_effect=RuntimeError('{"code":"invalid_api_key"}'),
        ):
            response = self.client.post(
                "/api/transcribe",
                files={"audio": ("voice.webm", b"audio", "audio/webm")},
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Groq rejected the API key", response.json()["detail"])
        self.assertIn("console.groq.com", response.json()["detail"])

    def test_transcribe_invalid_groq_key_is_actionable_in_hindi(self) -> None:
        with patch(
            "app.main.transcribe_audio",
            side_effect=RuntimeError('{"code":"invalid_api_key"}'),
        ):
            response = self.client.post(
                "/api/transcribe?language=hi",
                files={"audio": ("voice.webm", b"audio", "audio/webm")},
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Groq ने API key स्वीकार नहीं की", response.json()["detail"])

    def test_audio_question_uses_transcription(self) -> None:
        with patch("app.main.transcribe_audio", return_value="तीन महीने से वेतन नहीं मिला"):
            response = self.client.post(
                "/api/ask",
                files={"audio": ("voice.webm", b"audio", "audio/webm")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("वेतन", response.json()["transcript"])
        self.guidance_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()