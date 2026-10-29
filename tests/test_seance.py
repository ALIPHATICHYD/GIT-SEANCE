import io
import json
import os
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "demo"))

import haunted_house  # noqa: E402
from seance import cli, git, ofrenda, spirit, theatre  # noqa: E402
from seance.llm import Medium, ScriptedMedium  # noqa: E402


class HauntedRepo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = haunted_house.build(os.path.join(cls.tmp.name, "house"))
        theatre.configure(plain=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_blame_finds_the_revert(self):
        h = spirit.gather("lantern/printer.py", 9, cwd=self.repo)
        self.assertEqual(h.blame.author, "Marcus Bell")
        self.assertIn("Revert", h.commit.subject)
        subjects = [c.subject for c in h.history]
        self.assertIn("wait for the printer to wake up", subjects)
        self.assertFalse(h.is_summoner)

    def test_summoner_twist(self):
        h = spirit.gather("lantern/till.py", 1, cwd=self.repo)
        self.assertEqual(h.blame.author, "You")
        self.assertTrue(h.is_summoner)
        system = spirit.summon_messages(h, "why 37?")[0]["content"]
        self.assertIn("IS you", system)

    def test_prompt_carries_evidence(self):
        h = spirit.gather("lantern/printer.py", 9, cwd=self.repo)
        user = spirit.summon_messages(h, "why?")[1]["content"]
        self.assertIn("time.sleep(0.3)", user)
        self.assertIn(git.short(h.commit.sha), user)
        self.assertIn("The printer screamed", user)

    def test_citations_are_checked(self):
        h = spirit.gather("lantern/printer.py", 9, cwd=self.repo)
        real = git.short(h.commit.sha)
        cites = spirit.verify(f"I did it in [{real}], not in [1234abc]. Decade.", h.known_shas, self.repo)
        by = {c.token: c for c in cites}
        self.assertTrue(by[real].in_evidence)
        self.assertFalse(by["1234abc"].real)
        self.assertNotIn("decade", by)

    def test_census_and_departed(self):
        spirits = git.census(self.repo)
        now = git.latest_commit_time(self.repo)
        edna = spirits["edna@lanternworks.example"]
        self.assertEqual(edna.commits, 4)
        self.assertEqual(edna.last_words, "leave the light on for whoever comes next")
        self.assertTrue(edna.departed(now, 365))
        self.assertFalse(spirits["priya@lanternworks.example"].departed(now, 365))
        self.assertGreater(edna.surviving_lines, 0)

    def test_remembrance_facts(self):
        r = spirit.remember("edna", self.repo)
        self.assertEqual(r.first.subject, "lantern: first light")
        self.assertEqual(r.night_share, 1.0)
        html = ofrenda.render(r, "## In memory of Edna\n\n> leave the light on\n\n- a candle *always*", "gemma3:4b")
        self.assertIn("<blockquote>leave the light on</blockquote>", html)
        self.assertIn("<em>always</em>", html)
        self.assertIn("Edna Voss", html)

    def test_epitaph_parsing(self):
        self.assertEqual(spirit.parse_epitaphs("1. Kept the light on.\n2) \"Never again\"\nnoise", 3),
                         ["Kept the light on.", "Never again", ""])
        self.assertEqual(spirit.parse_epitaphs("1. Edna Voss: May her code shine.", 1), ["May her code shine."])

    def test_scripted_summon_end_to_end(self):
        h = spirit.gather("lantern/printer.py", 9, cwd=self.repo)
        medium = ScriptedMedium(f"I put it back in [{git.short(h.commit.sha)}]. Edna was right.")
        cwd = os.getcwd()
        os.chdir(self.repo)
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                cli.cmd_summon(type("A", (), {"target": "lantern/printer.py:9", "question": "why?", "once": True})(), medium)
        finally:
            os.chdir(cwd)
        self.assertIn("sealed in git history", buf.getvalue())
        self.assertIn("Edna was right", buf.getvalue())


class OllamaStream(unittest.TestCase):
    def test_streams_ollama_chunks(self):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                assert body["model"] == "gemma3:4b" and body["stream"] is True
                self.send_response(200)
                self.end_headers()
                for piece, done in (("Boo", False), (", mortal.", False), ("", True)):
                    self.wfile.write(json.dumps({"message": {"content": piece}, "done": done}).encode() + b"\n")

            def log_message(self, *a):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            m = Medium(model="gemma3:4b", backend="ollama", host=f"http://127.0.0.1:{server.server_port}")
            self.assertEqual("".join(m.channel([{"role": "user", "content": "hi"}])), "Boo, mortal.")
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
