import json
from pathlib import Path
from unittest.mock import patch

from lib.agents import pedigree_describer_agent as pda


async def test_analyze_pedigree_image_resolves_mapped_path():
    image_map = {0: Path('/tmp/img0.png'), 2: Path('/tmp/img2.png')}
    agent = pda.pedigree_describer_agent_for_images(image_map)
    (tool,) = agent.tools

    with patch.object(pda, 'describe_image', return_value='pedigree details') as mock:
        result = await tool.on_invoke_tool(None, json.dumps({'image_ref': 2}))

    assert result == 'pedigree details'
    mock.assert_called_once_with(Path('/tmp/img2.png'), pda.PEDIGREE_VISION_PROMPT)


async def test_analyze_pedigree_image_unknown_ref_is_recoverable():
    image_map = {0: Path('/tmp/img0.png'), 1: Path('/tmp/img1.png')}
    agent = pda.pedigree_describer_agent_for_images(image_map)
    (tool,) = agent.tools

    with patch.object(pda, 'describe_image') as mock:
        result = await tool.on_invoke_tool(None, json.dumps({'image_ref': 9}))

    # No VLM call for a hallucinated reference; the model gets a usable message back.
    mock.assert_not_called()
    assert 'No image with reference 9' in result
    assert '0, 1' in result
