from fastapi.templating import Jinja2Templates

from app.auth import get_csrf_token

templates = Jinja2Templates(directory="app/templates")
templates.env.globals["csrf_token"] = get_csrf_token
