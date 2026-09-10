"""ImagineClient multi-image URL extraction and collect/backfill behavior."""

from __future__ import annotations

import unittest

from scripts.poem_visualizer.imagine_client import (
    ImagineClient,
    ImagineResult,
    _extract_image_url,
    _extract_image_urls,
)


class ExtractImageUrlsTests(unittest.TestCase):
    def test_openai_compatible_data_list(self) -> None:
        data = {
            "data": [
                {"url": "https://example.com/a.jpg"},
                {"url": "https://example.com/b.jpg"},
                {"url": "https://example.com/c.jpg"},
            ]
        }
        urls = _extract_image_urls(data)
        self.assertEqual(
            urls,
            [
                "https://example.com/a.jpg",
                "https://example.com/b.jpg",
                "https://example.com/c.jpg",
            ],
        )
        self.assertEqual(_extract_image_url(data), "https://example.com/a.jpg")

    def test_top_level_url_and_images_alias(self) -> None:
        self.assertEqual(
            _extract_image_urls({"url": "https://example.com/one.jpg"}),
            ["https://example.com/one.jpg"],
        )
        self.assertEqual(
            _extract_image_urls(
                {"images": [{"url": "https://example.com/x.jpg"}, {"url": "https://example.com/y.jpg"}]}
            ),
            ["https://example.com/x.jpg", "https://example.com/y.jpg"],
        )

    def test_empty_and_b64_only_are_empty(self) -> None:
        self.assertEqual(_extract_image_urls({}), [])
        self.assertEqual(_extract_image_urls({"data": [{"b64_json": "xxxx"}]}), [])
        self.assertIsNone(_extract_image_url({}))

    def test_dedupes_and_strips(self) -> None:
        data = {
            "data": [
                {"url": " https://example.com/a.jpg "},
                {"url": "https://example.com/a.jpg"},
            ]
        }
        self.assertEqual(_extract_image_urls(data), ["https://example.com/a.jpg"])


class _FakeImagine:
    """Stand-in with generate_image only — collect_image_urls is unbound-called."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def generate_image(self, prompt, *, aspect_ratio="9:16", n=1):
        self.calls.append({"prompt": prompt, "aspect_ratio": aspect_ratio, "n": n})
        if not self._responses:
            return ImagineResult(ok=False, error="no more responses")
        return self._responses.pop(0)


class CollectImageUrlsTests(unittest.TestCase):
    def test_batch_n_returns_all_urls_without_backfill(self) -> None:
        fake = _FakeImagine(
            [
                ImagineResult(
                    ok=True,
                    url="http://a",
                    urls=["http://a", "http://b", "http://c", "http://d"],
                )
            ]
        )
        result = ImagineClient.collect_image_urls(
            fake, "toast prompt", aspect_ratio="4:3", n=4
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.urls, ["http://a", "http://b", "http://c", "http://d"])
        self.assertEqual(result.url, "http://a")
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(fake.calls[0]["n"], 4)
        self.assertEqual(fake.calls[0]["aspect_ratio"], "4:3")

    def test_single_url_batch_is_backfilled_sequentially(self) -> None:
        fake = _FakeImagine(
            [
                ImagineResult(ok=True, url="http://a", urls=["http://a"]),
                ImagineResult(ok=True, url="http://b", urls=["http://b"]),
                ImagineResult(ok=True, url="http://c", urls=["http://c"]),
            ]
        )
        result = ImagineClient.collect_image_urls(
            fake, "toast prompt", aspect_ratio="4:3", n=3
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.urls, ["http://a", "http://b", "http://c"])
        self.assertEqual([c["n"] for c in fake.calls], [3, 1, 1])

    def test_failed_batch_falls_back_to_singles(self) -> None:
        fake = _FakeImagine(
            [
                ImagineResult(ok=False, error="Image API HTTP 400: n not supported"),
                ImagineResult(ok=True, url="http://a", urls=["http://a"]),
                ImagineResult(ok=True, url="http://b", urls=["http://b"]),
            ]
        )
        result = ImagineClient.collect_image_urls(
            fake, "toast prompt", aspect_ratio="4:3", n=2
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.urls, ["http://a", "http://b"])
        self.assertIn("n not supported", result.error or "")

    def test_n1_failure_is_not_retried(self) -> None:
        fake = _FakeImagine([ImagineResult(ok=False, error="down")])
        result = ImagineClient.collect_image_urls(
            fake, "toast prompt", aspect_ratio="4:3", n=1
        )
        self.assertFalse(result.ok)
        self.assertEqual(len(fake.calls), 1)
        self.assertIn("down", result.error or "")


if __name__ == "__main__":
    unittest.main()
