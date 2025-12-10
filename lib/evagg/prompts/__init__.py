from pathlib import Path
from typing import Any, NamedTuple, Type

from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel

# Templates relative to this __init__.py
template_dir = Path(__file__).parent / 'templates'
env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)


class EmptyModel(BaseModel, extra='forbid'):
    pass


class PromptSpec(NamedTuple):
    template_name: str
    input_model: Type[BaseModel]
    output_model: Type[BaseModel]

    def render_template(self, **kwargs: Any) -> str:
        validated = self.input_model(**kwargs)
        template = env.get_template(self.template_name)
        return template.render(**validated.model_dump())


PROMPT_REGISTRY = {
    'system': PromptSpec(
        template_name='system.jinja2',
        input_model=EmptyModel,
        output_model=EmptyModel,
    ),
}

__all__ = ['PROMPT_REGISTRY']
