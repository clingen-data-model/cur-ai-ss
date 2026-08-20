import io
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from lib.agents.table_correction_agent import (
    ROTATIONS,
    RotationChoice,
    _rotated_object_path,
    _rotated_png_bytes,
    _table_shape,
    extract_best_rotation,
)

# Shapes taken from paper 81 (PMID 33232676), whose Table 1 is typeset sideways.
REFUSAL = (
    '| Error |\n|---|\n| Sorry, the image resolution/rotation prevents accurate OCR. |'
)
GOOD_TABLE = (
    '| Family-Individual | Sex | Age (years) of Onset (age at ESRD) | Variant |\n'
    '|---|---|---|---|\n'
    '| A3174-21 | M | 2 (4) | GBD |\n'
    '| HN-F25 | M | 8 (11) | DAD |'
)


def test_table_shape_rejects_refusal():
    columns, data_rows = _table_shape(REFUSAL)
    assert columns == 1
    assert data_rows == 1


def test_table_shape_counts_real_table():
    assert _table_shape(GOOD_TABLE) == (4, 2)


def test_table_shape_handles_non_table():
    assert _table_shape('I cannot read this image.') == (0, 0)


def test_rotated_png_bytes_swaps_axes_without_writing(tmp_path: Path):
    src = tmp_path / '0.png'
    Image.new('RGB', (535, 2717), 'white').save(src)

    data = _rotated_png_bytes(src, 90)

    assert Image.open(io.BytesIO(data)).size == (2717, 535)
    # Only the original crop exists; rotations are never persisted.
    assert [p.name for p in tmp_path.iterdir()] == ['0.png']


def test_rotated_object_path_is_namespaced_per_rotation(tmp_path: Path):
    assert _rotated_object_path(tmp_path / '0.png', 270).endswith('0.rot270.png')


def _choice(choice: RotationChoice) -> MagicMock:
    """Wrap a RotationChoice the way chat.completions.parse returns it."""
    parsed = MagicMock()
    parsed.choices[0].message.parsed = choice
    return parsed


def _run_tool(
    tmp_path: Path, by_rotation: dict[int, str], choice: RotationChoice
) -> str:
    """Run the extraction with a canned vision response per rotation."""
    src = tmp_path / '0.png'
    Image.new('RGB', (535, 2717), 'white').save(src)

    seen: list[int] = []

    def fake_create(**kwargs):
        # Recover which rotation this call carries from the stubbed URL.
        url = kwargs['messages'][0]['content'][0]['image_url']['url']
        degrees = int(url.rsplit('rot', 1)[1].split('.')[0]) if 'rot' in url else 0
        seen.append(degrees)
        response = MagicMock()
        response.choices[0].message.content = by_rotation[degrees]
        return response

    client = MagicMock()
    client.chat.completions.create.side_effect = fake_create
    client.chat.completions.parse.return_value = _choice(choice)

    with (
        patch('lib.agents.table_correction_agent.OpenAI', return_value=client),
        patch(
            'lib.agents.table_correction_agent.upload_and_sign_image',
            return_value='https://example.com/0.png',
        ),
        patch(
            'lib.agents.table_correction_agent.upload_and_sign_image_bytes',
            side_effect=lambda data, object_path: f'https://example.com/{object_path}',
        ),
    ):
        result = extract_best_rotation(src, 'scrambled reference')

    assert sorted(seen) == sorted(ROTATIONS), 'every rotation must be uploaded'
    # Rotations are uploaded, never persisted.
    assert [f.name for f in tmp_path.iterdir()] == ['0.png']
    return result


def test_tool_returns_the_rotation_the_model_picks(tmp_path: Path):
    """Only 270 transcribes; the other three refuse."""
    result = _run_tool(
        tmp_path,
        {0: REFUSAL, 90: REFUSAL, 180: REFUSAL, 270: GOOD_TABLE},
        RotationChoice(best_rotation=270, any_usable=True, reasoning='upright'),
    )
    assert result == GOOD_TABLE


def test_tool_returns_the_pick_verbatim_not_a_rerendering(tmp_path: Path):
    """The chosen candidate is passed through byte-for-byte."""
    thinner = '| A | B | C |\n|---|---|---|\n| 1 | 2 | 3 |'
    result = _run_tool(
        tmp_path,
        {0: thinner, 90: REFUSAL, 180: REFUSAL, 270: GOOD_TABLE},
        RotationChoice(best_rotation=270, any_usable=True, reasoning='more faithful'),
    )
    assert result == GOOD_TABLE


def test_tool_defers_to_the_model_over_table_size(tmp_path: Path):
    """A wider candidate does not win if the model judges another more faithful."""
    wider = '| A | B | C | D | E | F |\n|---|---|---|---|---|---|\n| 1 | 2 | 3 | 4 | 5 | 6 |'
    result = _run_tool(
        tmp_path,
        {0: wider, 90: REFUSAL, 180: REFUSAL, 270: GOOD_TABLE},
        RotationChoice(
            best_rotation=270, any_usable=True, reasoning='wider is garbled'
        ),
    )
    assert result == GOOD_TABLE


def test_tool_falls_back_when_no_rotation_reads(tmp_path: Path):
    result = _run_tool(
        tmp_path,
        dict.fromkeys(ROTATIONS, REFUSAL),
        RotationChoice(best_rotation=0, any_usable=False, reasoning='all refused'),
    )
    assert result == REFUSAL


def test_tool_falls_back_when_the_model_names_an_unknown_rotation(tmp_path: Path):
    result = _run_tool(
        tmp_path,
        {0: REFUSAL, 90: REFUSAL, 180: REFUSAL, 270: GOOD_TABLE},
        RotationChoice(best_rotation=45, any_usable=True, reasoning='bogus'),
    )
    assert result == REFUSAL
