# !/usr/bin/env python
import os
# Migrated to FastAPI from webapp2
from fastapi import FastAPI, Request  # type: ignore
from fastapi.responses import HTMLResponse, RedirectResponse  # type: ignore
from fastapi.staticfiles import StaticFiles  # type: ignore
import jinja2

# Jinja2 environment remains same as before
JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=[],
    autoescape=True)

# Original config for webapp2 sessions remains for reference (not used in FastAPI)
config = {'webapp2_extras.sessions': dict(secret_key='93986c9cdd240540f70efaea56a9e3f2')}

app = FastAPI()

# Mount static directory
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def main(request: Request):
    # Render index.html template for the root URL
    template = JINJA_ENVIRONMENT.get_template('index.html')
    return HTMLResponse(content=template.render({}))

@app.get("/{full_path:path}", response_class=HTMLResponse)
async def catch_all(request: Request, full_path: str):
    # If the URL ends with a slash, redirect to the non-slash version
    if request.url.path.endswith("/") and request.url.path != "/":
        new_url = request.url.path.rstrip("/")
        if request.url.query:
            new_url += "?" + request.url.query
        return RedirectResponse(url=new_url)
    # For all other routes, respond with a 404 and render index.html
    template = JINJA_ENVIRONMENT.get_template('index.html')
    return HTMLResponse(content=template.render({}), status_code=404)
