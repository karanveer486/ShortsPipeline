import unittest


class PackageFoundationTests(unittest.TestCase):
    def test_version_is_exposed(self) -> None:
        from shorts_pipeline import __version__

        self.assertEqual(__version__, "0.1.0")


if __name__ == "__main__":
    unittest.main()
