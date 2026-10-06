import io
import shutil

import pytest
from docling_core.types.doc import (
    BoundingBox,
    CoordOrigin,
    DoclingDocument,
    ImageRef,
    PictureItem,
    ProvenanceItem,
    Size,
)
from PIL import Image

from lib.misc.pdf.convert_result import (
    ConvertResult,
    load_convert_result,
    save_convert_result,
)
from lib.misc.pdf.words import WordLoc


def _png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, 'PNG')
    return buf.getvalue()


def _result() -> ConvertResult:
    doc = DoclingDocument(name='test')
    doc.add_page(page_no=1, size=Size(width=600, height=800))
    crop = Image.new('RGB', (40, 30), (200, 10, 10))
    doc.add_picture(
        image=ImageRef.from_pil(crop, dpi=288),
        prov=ProvenanceItem(
            page_no=1,
            bbox=BoundingBox(
                l=10, t=400, r=300, b=340, coord_origin=CoordOrigin.BOTTOMLEFT
            ),
            charspan=(0, 0),
        ),
    )
    word = WordLoc(
        page_idx=0, word='gene', x0=1, y0=2, x1=3, y1=2, x2=3, y2=4, x3=1, y3=4
    )
    return ConvertResult(document=doc, words=[word])


def _picture_png(result: ConvertResult) -> bytes:
    (picture,) = result.document.pictures
    assert isinstance(picture, PictureItem)
    image = picture.get_image(result.document)
    assert image is not None
    return _png_bytes(image)


def test_round_trip_preserves_pictures_and_words(tmp_path):
    original = _result()
    json_path, words_path = tmp_path / 'raw.json', tmp_path / 'words.json'

    save_convert_result(original, json_path, words_path)
    loaded = load_convert_result(json_path, words_path)

    assert _picture_png(loaded) == _picture_png(original)
    assert loaded.words == original.words
    assert (tmp_path / 'raw_artifacts').is_dir()


def test_load_needs_artifacts_at_the_path_they_were_written_to(tmp_path):
    """Pictures are referenced by absolute path, so the reader must restore them
    at the writer's path -- moving only the JSON is not enough."""
    original = _result()
    json_path, words_path = tmp_path / 'raw.json', tmp_path / 'words.json'
    save_convert_result(original, json_path, words_path)
    shutil.move(tmp_path / 'raw_artifacts', tmp_path / 'elsewhere')

    loaded = load_convert_result(json_path, words_path)
    with pytest.raises(FileNotFoundError):
        _picture_png(loaded)

    shutil.move(tmp_path / 'elsewhere', tmp_path / 'raw_artifacts')
    assert _picture_png(load_convert_result(json_path, words_path)) == _picture_png(
        original
    )
