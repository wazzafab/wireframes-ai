import os
import shutil
import subprocess
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

APP_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = APP_ROOT / "web_runs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PIPELINE_CMD = ["python", "build_pipeline.py"]

# Your pipeline expects this filename
PIPELINE_INPUT_NAME = "input.docx"

app = FastAPI(title="Wireframe Builder", version="0.1")
# Serve UI + static assets
app.mount("/static", StaticFiles(directory=str(APP_ROOT / "static")), name="static")

# Serve run artifacts (SVGs + JSON) by run_id
app.mount("/runs", StaticFiles(directory=str(OUTPUT_DIR)), name="runs")

@app.get("/")
def home():
    return FileResponse(str(APP_ROOT / "static" / "index.html"))



@app.post("/build")
async def build(file: UploadFile = File(...)):
    run_id = uuid.uuid4().hex[:10]
    run_dir = OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Copy project files into run folder (so runs are isolated)
        # Exclude folders that can contaminate a run (previous outputs, caches)
        EXCLUDE_DIRS = {"web_runs", "rendered_wireframes", "__pycache__", ".git"}
        EXCLUDE_FILES = {"wireframes.json", "wireframes.enriched.json", "semantic.json", "sitemap.json", "facts.json"}

        for item in APP_ROOT.iterdir():
            if item.name in EXCLUDE_DIRS:
                continue

            if item.is_dir():
                shutil.copytree(item, run_dir / item.name, dirs_exist_ok=True)
            else:
                if item.name in EXCLUDE_FILES:
                    continue
                shutil.copy2(item, run_dir / item.name)

        # Ensure no stale renders exist in the run folder
        stale_render_dir = run_dir / "rendered_wireframes"
        if stale_render_dir.exists():
            shutil.rmtree(stale_render_dir)
        # Ensure no stale structural artifacts exist
        for stale_file in [
            "sitemap.json",
            "wireframes.json",
            "wireframes.enriched.json",
            "semantic.json",
            "facts.json",
        ]:
            p = run_dir / stale_file
            if p.exists():
                p.unlink()    

        # IMPORTANT: write uploaded doc LAST so nothing overwrites it
        input_path = run_dir / PIPELINE_INPUT_NAME
        with open(input_path, "wb") as f:
            f.write(await file.read())

        # Run the pipeline inside the run folder
        result = subprocess.run(
            PIPELINE_CMD,
            cwd=str(run_dir),
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise HTTPException(
                status_code=400,
                detail={
                    "run_id": run_id,
                    "error": "Pipeline failed",
                    "stdout": result.stdout[-4000:],
                    "stderr": result.stderr[-4000:],
                },
            )

        # Return key output locations
        return JSONResponse(
            {
                "run_id": run_id,
                "artifacts": {
                    "sitemap": str((run_dir / "sitemap.json").relative_to(APP_ROOT)),
                    "facts": str((run_dir / "facts.json").relative_to(APP_ROOT)),
                    "semantic": str((run_dir / "semantic.json").relative_to(APP_ROOT)),
                    "wireframes_enriched": str((run_dir / "wireframes.enriched.json").relative_to(APP_ROOT)),
                    "rendered_dir": str((run_dir / "rendered_wireframes").relative_to(APP_ROOT)),
                },
                "stdout_tail": result.stdout[-2000:],
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"run_id": run_id, "error": str(e)})
