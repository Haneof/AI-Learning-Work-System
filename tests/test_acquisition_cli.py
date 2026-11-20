"""CLI contract tests for the discovery command."""

from aios_work_system.cli import build_parser


def test_discover_search_cli_requires_keyword_and_accepts_platform_options():
    parser = build_parser()
    args = parser.parse_args(
        [
            "discover-search",
            "--platform",
            "bilibili",
            "--keyword",
            "python tutorial",
            "--page",
            "2",
            "--page-size",
            "10",
        ]
    )

    assert args.command == "discover-search"
    assert args.platform == "bilibili"
    assert args.keyword == "python tutorial"
    assert args.page == 2
    assert args.page_size == 10
    assert args.database.endswith("candidates.sqlite3")
