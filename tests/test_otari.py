"""git-seance against a fake Otari gateway: streaming, receipts, letters, tribunal, catalog."""

import io
import json
import os
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "demo"))

import haunted_house  # noqa: E402
from seance import cli, git, spirit, theatre, tribunal  # noqa: E402
from seance.llm import MediumError, OtariMedium  # noqa: E402
from seance.otari import Otari, pick_panel  # noqa: E402


class FakeOtari(BaseHTTPRequestHandler):
    """Speaks just enough of Otari's API. The reply depends on the model, so a tribunal has a liar."""

    seen: list = []
    sha = "0000000"

    def log_message(self, *a):
        pass

    def _json(self, code, obj, headers=None):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        FakeOtari.seen.append(("GET", self.path, self.headers.get("Authorization"), None))
        if self.path.startswith("/api/v1/catalog/models"):
            return self._json(200, {"count": 4, "models": [
                {"id": "openai/gpt-oss-120b", "selector": "openai/gpt-oss-120b", "open_weights": True,
                 "min_input_price_per_million": 0.1, "min_output_price_per_million": 0.5},
                {"id": "google/gemma-3-27b-it", "open_weights": True},
                {"id": "qwen/qwen3-32b", "open_weights": True},
                {"id": "openai/gpt-5", "open_weights": False},
            ]})
        if self.path == "/api/v1/key/budget":
            return self._json(200, {"budgets_enforced": True, "remaining_usd": 19.5, "limits": []})
        self._json(404, {"detail": "nope"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
        FakeOtari.seen.append(("POST", self.path, self.headers.get("Authorization"), body))
        if self.path == "/api/v1/fetch":
            return self._json(200, {"object": "fetch", "url": body["url"], "title": "ESC/P",
                                    "text": "ESC @ initializes the printer."})
        if self.path != "/api/v1/chat/completions":
            return self._json(404, {"detail": "nope"})
        model = body["model"]
        if model == "broken/model":
            return self._json(424, {"detail": "no provider"}, {"Otari-Error-Code": "provider_not_configured"})
        if "qwen" in model:
            words = ["I", " did", " it", " in", " [dead123].", " Trust", " me."]
        elif "gemma" in model:
            words = ["My", " memory", " fades."]
        else:
            words = ["I", " put", " it", " back", f" in [{FakeOtari.sha}]."]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Otari-Request-ID", "req_123")
        self.send_header("Otari-Provider", "groq")
        self.send_header("Otari-Model", model)
        self.send_header("Otari-Attempt-Count", "2" if "gemma" in model else "1")
        self.send_header("Otari-Fallback", "true" if "gemma" in model else "false")
        self.send_header("Otari-Response-Duration-Ms", "812")
        self.end_headers()
        chunks = [{"choices": [{"delta": {}, "index": 0}],
                   "otari_tool_calls": [{"id": "otari_wf_1", "type": "web_fetch", "status": "completed",
                                         "url": "https://example.org"}]}]
        chunks += [{"choices": [{"delta": {"content": w}, "index": 0}]} for w in words]
        chunks.append({"choices": [], "usage": {"prompt_tokens": 900, "completion_tokens": 40,
                                                "cost_usd": "0.000123", "pricing_source": "defaults"}})
        for c in chunks:
            self.wfile.write(f"data: {json.dumps(c)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")


class OtariSwitchboard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = haunted_house.build(os.path.join(cls.tmp.name, "house"))
        theatre.configure(plain=True)
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeOtari)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.client = Otari(key="tk-test", base=f"http://127.0.0.1:{cls.srv.server_port}/api")
        h = spirit.gather("lantern/printer.py", 9, cwd=cls.repo)
        FakeOtari.sha = git.short(h.commit.sha)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()

    def setUp(self):
        FakeOtari.seen.clear()

    def test_base_url_forms(self):
        self.assertEqual(Otari(key="k", base="https://eu.api.otari.ai/api").base, "https://eu.api.otari.ai/api/v1")
        self.assertEqual(Otari(key="k", base="https://api.otari.ai").base, "https://api.otari.ai/api/v1")
        self.assertEqual(Otari(key="k", base="http://localhost:8000/api/v1/").base, "http://localhost:8000/api/v1")

    def test_stream_and_receipt(self):
        m = OtariMedium(model="openai/gpt-oss-120b", client=self.client)
        text = "".join(m.channel([{"role": "user", "content": "hi"}]))
        self.assertIn("I put it back", text)
        r = m.last
        self.assertEqual((r.request_id, r.provider, r.model), ("req_123", "groq", "openai/gpt-oss-120b"))
        self.assertAlmostEqual(r.cost_usd, 0.000123)
        self.assertEqual(r.completion_tokens, 40)
        self.assertEqual(r.tool_calls[0]["type"], "web_fetch")
        self.assertIn("$0.000123", r.line())
        method, path, auth, body = FakeOtari.seen[-1]
        self.assertEqual(auth, "Bearer tk-test")
        self.assertEqual(body["metadata"], {"app": "git-seance", "ritual": "summon"})
        self.assertTrue(body["stream_options"]["include_usage"])

    def test_fallback_is_reported(self):
        m = OtariMedium(model="google/gemma-3-27b-it", client=self.client)
        "".join(m.channel([{"role": "user", "content": "hi"}]))
        self.assertTrue(m.last.fallback)
        self.assertIn("fallback fired", m.last.line())

    def test_errors_become_medium_errors(self):
        m = OtariMedium(model="broken/model", client=self.client)
        with self.assertRaises(MediumError) as e:
            "".join(m.channel([{"role": "user", "content": "hi"}]))
        self.assertIn("424", str(e.exception))
        self.assertIn("provider_not_configured", str(e.exception))

    def test_missing_key_is_explained(self):
        m = OtariMedium(model="x", client=Otari(key="", base="http://127.0.0.1:9"))
        with self.assertRaises(MediumError) as e:
            "".join(m.channel([]))
        self.assertIn("OTARI_API_KEY", str(e.exception))

    def test_letters_are_found_and_read(self):
        h = spirit.gather("lantern/printer.py", 9, cwd=self.repo)
        found = spirit.find_letters(h, "https://github.com/lantern/lantern")
        self.assertEqual(found[0].url, "https://en.wikipedia.org/wiki/ESC/P")
        h.letters = spirit.read_letters(found, self.client.fetch)
        self.assertEqual(h.letters[0].title, "ESC/P")
        blank = spirit.read_letters([spirit.Letter("https://en.wikipedia.org/wiki/ESC/P", "x")], lambda u: {"text": "t"})
        self.assertEqual(blank[0].title, "ESC/P")
        user = spirit.summon_messages(h, "why?")[1]["content"]
        self.assertIn("[letter 1]", user)
        self.assertIn("ESC @ initializes the printer.", user)
        system = spirit.summon_messages(h, "why?")[0]["content"]
        self.assertIn("cite it as [letter N]", system)
        self.assertEqual(spirit.cited_letters("as [letter 1] says, and [letter 9]", 1), [1])
        self.assertEqual(spirit.cited_letters("bytes [letter\u202f1].", 1), [1])

    def test_issue_refs_become_urls(self):
        h = spirit.gather("lantern/printer.py", 9, cwd=self.repo)
        h.commit = git.Commit("a" * 40, "x", "x@x", 0, "fix the till (#42)", "")
        h.history = []
        urls = [le.url for le in spirit.find_letters(h, "https://github.com/mozilla-ai/otari")]
        self.assertEqual(urls, ["https://github.com/mozilla-ai/otari/issues/42"])

    def test_tribunal_finds_the_liar(self):
        h = spirit.gather("lantern/printer.py", 9, cwd=self.repo)
        heard = tribunal.convene(["qwen/qwen3-32b", "openai/gpt-oss-120b", "google/gemma-3-27b-it"],
                                 spirit.summon_messages(h, "why?"), h.known_shas, self.repo, self.client)
        verdicts = {t.model: t.verdict for t in heard}
        self.assertEqual(heard[0].model, "openai/gpt-oss-120b")
        self.assertEqual(verdicts["openai/gpt-oss-120b"], "honest")
        self.assertEqual(verdicts["qwen/qwen3-32b"], "LIAR")
        self.assertEqual(verdicts["google/gemma-3-27b-it"], "silent (cited nothing)")
        md = tribunal.report(h, "why?", heard)
        self.assertIn("**The honest medium:** `openai/gpt-oss-120b`", md)
        self.assertIn("**does not exist**", md)
        tags = [b["metadata"]["ritual"] for m, p, a, b in FakeOtari.seen if p.endswith("/chat/completions")]
        self.assertEqual(tags, ["tribunal"] * 3)

    def test_catalog_panel_is_open_weight_and_diverse(self):
        models = self.client.open_weight_models()
        self.assertNotIn("openai/gpt-5", [m["id"] for m in models])
        self.assertEqual(models[0]["id"], "openai/gpt-oss-120b")  # priced first, then unpriced by id
        self.assertEqual(pick_panel(models), ["google/gemma-3-27b-it", "qwen/qwen3-32b", "openai/gpt-oss-120b"])

    def test_cli_tribunal_end_to_end(self):
        out_md = os.path.join(self.tmp.name, "record.md")
        cwd = os.getcwd()
        os.chdir(self.repo)
        buf = io.StringIO()
        try:
            medium = OtariMedium(client=self.client)
            args = type("A", (), {"target": "lantern/printer.py:9", "question": "why?", "models": None, "size": 3,
                                  "no_letters": False, "output": out_md})()
            with redirect_stdout(buf):
                cli.cmd_tribunal(args, medium)
        finally:
            os.chdir(cwd)
        text = buf.getvalue()
        self.assertIn("The honest medium is openai/gpt-oss-120b", text)
        self.assertIn("[letter 1] https://en.wikipedia.org/wiki/ESC/P", text)
        self.assertIn("the whole tribunal cost $0.000369", text)
        self.assertTrue(os.path.exists(out_md))

    def test_cli_mediums(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.cmd_mediums(type("A", (), {"limit": 10})(), OtariMedium(client=self.client))
        self.assertIn("openai/gpt-oss-120b", buf.getvalue())
        self.assertIn("$19.50", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
