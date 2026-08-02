import unittest

from backend.exporter.html_viewer import render_index_html


class HtmlViewerPaginationTests(unittest.TestCase):
    def test_renders_manual_page_inputs_in_both_pagers(self):
        content = render_index_html({"language": "en", "title": "Archive"}, variant="ledger")
        self.assertIn('id="page-input"', content)
        self.assertIn('id="page-input-bottom"', content)
        self.assertIn("goToPage(input)", content)
        self.assertIn("input.max = String(pages)", content)


if __name__ == "__main__":
    unittest.main()
