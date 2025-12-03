"""The evagg core library."""

from .app import PaperQueryApp, SinglePMIDApp
from .content import PromptBasedContentExtractor, PromptBasedContentExtractorCached
from .interfaces import IEvAggApp, IExtractFields, IGetPapers, IWriteOutput
from .io import JSONOutputWriter, TableOutputWriter
from .library import RareDiseaseFileLibrary, RareDiseaseLibraryCached, SinglePaperLibrary
from .simple import PropertyContentExtractor, SampleContentExtractor, SimpleFileLibrary
from .truthset import TruthsetFileHandler

__all__ = [
    # Interfaces.
    "IEvAggApp",
    "IGetPapers",
    "IExtractFields",
    "IWriteOutput",
    # App.
    "PaperQueryApp",
    "SinglePMIDApp",
    # IO.
    "TableOutputWriter",
    "JSONOutputWriter",
    # Library.
    "SimpleFileLibrary",
    "TruthsetFileHandler",
    "RareDiseaseFileLibrary",
    "RareDiseaseLibraryCached",
    "SinglePaperLibrary",
    # Content.
    "PromptBasedContentExtractor",
    "PromptBasedContentExtractorCached",
    "PropertyContentExtractor",
    "SampleContentExtractor",
]
