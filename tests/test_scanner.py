from pathlib import PurePosixPath

from codedoc.scanner import module_of, scan_repository


def test_scanner_skips_noise_and_secrets(sample_repo):
    result = scan_repository(sample_repo)
    paths = {f["path"] for f in result.files}
    assert "app/orders.py" in paths and "README.md" in paths
    assert ".env" not in paths
    assert "config/credentials.json" not in paths
    assert not any(p.startswith(("node_modules", "build")) for p in paths)
    assert "debug.log" not in paths and "package-lock.json" not in paths
    assert result.skipped_secrets == 2
    assert result.readme.startswith("# Shop")


def test_scanner_detects_stack(sample_repo):
    stack = scan_repository(sample_repo).stack
    assert {"Python", "FastAPI", "SQLAlchemy"} <= set(stack)


def test_scanner_prioritises_business_files(sample_repo):
    files = scan_repository(sample_repo).files
    order = [f["path"] for f in files]
    assert order[0] == "README.md"
    assert order.index("app/api/routes.py") < order.index("tests/test_orders.py")


def test_max_files_limit(sample_repo):
    result = scan_repository(sample_repo, max_files=2)
    assert len(result.files) == 2
    assert result.total_candidates > 2


def test_module_of():
    assert module_of(PurePosixPath("README.md")) == "(root)"
    assert module_of(PurePosixPath("billing/invoice.py")) == "billing"
    assert module_of(PurePosixPath("src/orders/service.py")) == "src/orders"
