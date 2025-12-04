import json
import logging
import os
import sys
from datetime import datetime
from typing import Mapping, Optional, Sequence

from lib.evagg.utils.run import get_run_path

logger = logging.getLogger(__name__)


class JSONOutputWriter:
    def __init__(self, json_name: Optional[str] = None) -> None:
        self._generated = datetime.now().astimezone()
        self._path = (
            os.path.join(get_run_path(), f"{json_name}.json") if json_name else None
        )

        if self._path and os.path.exists(self._path):
            logger.warning(f"Overwriting existing output file: {self._path}")

    def write(self, output: Sequence[Mapping[str, str]]) -> Optional[str]:
        logger.info(f"Writing output to: {self._path or 'stdout'}")

        if len(output) == 0:
            logger.warning("No results to write")
            return None

        # Create parent directories if needed
        if self._path:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)

        # Package JSON payload
        payload = {
            "generated": self._generated.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "results": list(output),
        }

        # Write to file or stdout
        output_stream = open(self._path, "w") if self._path else sys.stdout
        json.dump(payload, output_stream, indent=2)
        if self._path:
            output_stream.close()

        return self._path
