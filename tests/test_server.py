import pytest
from netmiko_mcp.server import main

def test_main_execution(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that the main entrypoint executes without errors and prints the expected initialization message."""
    main()
    captured = capsys.readouterr()
    assert "Netmiko MCP Server initializing..." in captured.out
