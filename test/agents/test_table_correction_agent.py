import json
from pathlib import Path
from unittest.mock import patch

from lib.agents import table_correction_agent


async def test_extract_table_tool_delegates_to_describe_image():
    image_path = Path('/tmp/table.png')
    agent = table_correction_agent.table_correction_agent_for_image(image_path)
    (tool,) = agent.tools

    with patch.object(
        table_correction_agent, 'describe_image', return_value='| a | b |'
    ) as mock:
        result = await tool.on_invoke_tool(None, json.dumps({}))

    assert result == '| a | b |'
    mock.assert_called_once_with(
        image_path, table_correction_agent.VISION_EXTRACTION_PROMPT
    )
