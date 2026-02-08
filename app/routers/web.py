from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

router = APIRouter()

_templates_dir = Path(__file__).resolve().parent.parent / "web" / "templates"
_env = Environment(loader=FileSystemLoader(str(_templates_dir)))


@router.get("/", response_class=HTMLResponse)
async def index():
    template = _env.get_template("index.html")
    return template.render()


@router.get("/admin", response_class=HTMLResponse)
async def admin():
    template = _env.get_template("admin.html")
    return template.render()
