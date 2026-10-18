"""Offline OG request checks; never load operational settings or write images."""
import importlib.util
import socket
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx


spec = importlib.util.spec_from_file_location(
    "fetch_og_under_test", Path(__file__).resolve().parents[1] / "fetch_og.py"
)
fetch_og = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"settings": types.SimpleNamespace(AGG_HOST="")}):
    spec.loader.exec_module(fetch_og)

HTTPX_CLIENT = httpx.Client
PUBLIC_V4 = "93.184.216.34"
PUBLIC_V6 = "2606:2800:220:1:248:1893:25c8:1946"


class PublicDestinationTests(unittest.TestCase):
    def setUp(self):
        self.addresses = {}
        self.sent = []
        self.replies = {}
        self.addCleanup(patch.stopall)
        patch.object(socket, "getaddrinfo", side_effect=self.resolve).start()
        patch.object(socket, "socket", side_effect=AssertionError("Network forbidden")).start()
        patch.object(fetch_og.httpx, "Client", side_effect=self.client).start()

    def resolve(self, host, port, **kwargs):
        return [
            (socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))
            for ip in self.addresses.get(host, [PUBLIC_V4])
        ]

    def client(self, **kwargs):
        return HTTPX_CLIENT(transport=httpx.MockTransport(self.respond), trust_env=False, **kwargs)

    def respond(self, request):
        self.sent.append(str(request.url))
        return self.replies.get(str(request.url), httpx.Response(
            200, headers={"Content-Type": "text/html"}, text="<html></html>"
        ))

    def test_public_addresses_and_relative_redirect_are_allowed(self):
        self.addresses["example.com"] = [PUBLIC_V4, PUBLIC_V6]
        self.replies["https://example.com/start"] = httpx.Response(302, headers={"Location": "/story"})
        result = fetch_og.work((1, "https://example.com/start", None))
        self.assertEqual(result, (1, None, "no og:image"))
        self.assertEqual(self.sent, ["https://example.com/start", "https://example.com/story"])

    def test_non_public_addresses_are_blocked_before_sending(self):
        blocked = [
            "127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.0.1", "169.254.169.254",
            "0.0.0.0", "100.64.0.1", "192.0.2.1", "198.18.0.1", "224.0.0.1", "240.0.0.1",
            "::", "::1", "fc00::1", "fe80::1", "ff02::1", "2001:db8::1", "::ffff:127.0.0.1",
        ]
        for ip in blocked:
            with self.subTest(address=ip):
                self.addresses["blocked.example"] = [ip]
                result = fetch_og.work((1, "https://blocked.example/story", None))
                self.assertIsNone(result[1])
                self.assertTrue(result[2].startswith("ValueError:"), result)
                self.assertEqual(self.sent, [])

    def test_mixed_public_and_private_dns_answers_are_blocked(self):
        self.addresses["example.com"] = [PUBLIC_V4, "::1"]
        self.assertIsNone(fetch_og.work((1, "https://example.com/story", None))[1])
        self.assertEqual(self.sent, [])

    def test_article_redirect_to_private_host_is_blocked(self):
        self.addresses["internal.example"] = ["10.0.0.1"]
        self.replies["https://example.com/story"] = httpx.Response(
            302, headers={"Location": "https://internal.example/story"}
        )
        result = fetch_og.work((1, "https://example.com/story", None))
        self.assertTrue(result[2].startswith("ValueError:"), result)
        self.assertEqual(self.sent, ["https://example.com/story"])

    def test_dns_is_checked_again_on_same_host_redirect(self):
        self.replies["https://example.com/start"] = httpx.Response(302, headers={"Location": "/story"})
        answers = iter([PUBLIC_V4, "127.0.0.1"])
        with patch.object(socket, "getaddrinfo", side_effect=lambda *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (next(answers), 443))
        ]):
            result = fetch_og.work((1, "https://example.com/start", None))
        self.assertTrue(result[2].startswith("ValueError:"), result)
        self.assertEqual(self.sent, ["https://example.com/start"])

    def test_private_image_and_image_redirect_are_blocked(self):
        self.addresses["internal.example"] = ["169.254.169.254"]
        for image in ("https://internal.example/image", "https://images.example.org/image"):
            with self.subTest(image=image):
                self.sent.clear()
                self.replies["https://example.com/story"] = httpx.Response(
                    200, headers={"Content-Type": "text/html"},
                    text=f'<meta property="og:image" content="{image}">'
                )
                self.replies["https://images.example.org/image"] = httpx.Response(
                    302, headers={"Location": "https://internal.example/image"}
                )
                result = fetch_og.work((1, "https://example.com/story", None))
                self.assertTrue(result[2].startswith("ValueError:"), result)
                expected = ["https://example.com/story"]
                if "images.example.org" in image:
                    expected.append(image)
                self.assertEqual(self.sent, expected)

    def test_public_image_request_preserves_referer_and_cache_result(self):
        self.replies["https://example.com/story"] = httpx.Response(
            200, headers={"Content-Type": "text/html"},
            text='<meta property="og:image" content="https://images.example.org/image">'
        )
        self.replies["https://images.example.org/image"] = httpx.Response(200, content=b"x" * 1200)

        def save(cl, iid, image, referer):
            response = cl.get(image, headers={"Referer": referer})
            self.assertEqual(response.request.headers["Referer"], "https://example.com/story")
            return f"og/{iid}.webp", None

        with patch.object(fetch_og, "save_image", side_effect=save):
            self.assertEqual(fetch_og.work((1, "https://example.com/story", None)), (1, "og/1.webp", None))
        self.assertEqual(self.sent, ["https://example.com/story", "https://images.example.org/image"])

    def test_unresolved_host_is_blocked(self):
        self.addresses["unresolved.example"] = []
        result = fetch_og.work((1, "https://unresolved.example/story", None))
        self.assertTrue(result[2].startswith("ValueError:"), result)
        with patch.object(socket, "getaddrinfo", side_effect=socket.gaierror("No address")):
            result = fetch_og.work((1, "https://unresolved.example/story", None))
        self.assertTrue(result[2].startswith("gaierror:"), result)
        self.assertEqual(self.sent, [])

    def test_other_schemes_are_blocked(self):
        for url in ("file:///private", "ftp://example.com/story"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    fetch_og.require_public_url(httpx.Request("GET", url))
        self.assertEqual(self.sent, [])

    def test_aggregator_original_url_is_checked(self):
        self.addresses["internal.example"] = ["192.168.0.1"]
        with patch.object(fetch_og.settings, "AGG_HOST", "news.example.net"):
            result = fetch_og.work((1, "https://news.example.net/articles/id", "https://internal.example/story"))
        self.assertTrue(result[2].startswith("ValueError:"), result)
        self.assertEqual(self.sent, [])

    def test_aggregator_endpoint_is_checked(self):
        self.addresses["news.example.net"] = ["127.0.0.1"]
        with patch.object(fetch_og.settings, "AGG_HOST", "news.example.net"):
            result = fetch_og.work((1, "https://news.example.net/articles/id", None))
        self.assertTrue(result[2].startswith("ValueError:"), result)
        self.assertEqual(self.sent, [])


if __name__ == "__main__":
    unittest.main()
