import os
from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from google import genai
from google.genai import types
from PIL import Image
from io import BytesIO
import base64
import time
import uuid
import json
import requests
from pathlib import Path
from typing import List, Dict

app = FastAPI()

# Configure static files and templates
app.mount("/static", StaticFiles(directory="static"), "static")
templates = Jinja2Templates(directory="templates")

# Initialize Gemini client with API key
GEMINI_API_KEY = os.getenv("GEMINI_BILLING_ACCOUNT")
client = genai.Client(api_key=GEMINI_API_KEY)

# Global storage for generated assets
GENERATED_ASSETS = {
    "characters": {},
    "scenes": {},
    "frames": [],
    "storyline": {},
    "final_video": None
}

# Ensure directories exist
Path("static/generated").mkdir(parents=True, exist_ok=True)
Path("static/characters").mkdir(parents=True, exist_ok=True)
Path("static/scenes").mkdir(parents=True, exist_ok=True)
Path("static/frames").mkdir(parents=True, exist_ok=True)

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/setup_story")
async def setup_story(
    story_title: str = Form(...),
    story_genre: str = Form(...),
    story_theme: str = Form(...),
    main_characters: int = Form(...),
    secondary_characters: int = Form(...),
    art_style: str = Form(...),
    camera_style: str = Form(...)
):
    GENERATED_ASSETS["storyline"] = {
        "title": story_title,
        "genre": story_genre,
        "theme": story_theme,
        "art_style": art_style,
        "camera_style": camera_style,
        "main_characters": main_characters,
        "secondary_characters": secondary_characters
    }
    
    return JSONResponse(content={"status": "success", "message": "Story setup completed"})

@app.post("/generate_character")
async def generate_character(
    character_type: str = Form(...),
    character_name: str = Form(...),
    character_description: str = Form(...),
    character_outfit: str = Form(...),
    character_expression: str = Form("neutral")
):
    prompt = f"""
    Generate a full-body reference image of a {character_type} character named {character_name} for our story.
    Character details: {character_description}
    Outfit: {character_outfit}
    Expression: {character_expression}
    Art style: {GENERATED_ASSETS["storyline"]["art_style"]}
    Camera style: {GENERATED_ASSETS["storyline"]["camera_style"]} - full body shot
    
    Important requirements:
    - Consistent proportions and features
    - Distinctive visual elements that can be recognized in other scenes
    - Neutral pose that shows all important features
    - High resolution and detailed
    """
    
    response = client.models.generate_content(
        model="gemini-2.0-flash-preview-image-generation",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=['TEXT', 'IMAGE']
        )
    )
    
    character_id = str(uuid.uuid4())
    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            image = Image.open(BytesIO((part.inline_data.data)))
            filename = f"static/characters/{character_id}.png"
            image.save(filename)
            
            GENERATED_ASSETS["characters"][character_id] = {
                "name": character_name,
                "type": character_type,
                "description": character_description,
                "outfit": character_outfit,
                "image_path": filename,
                "expressions": [character_expression]
            }
            
            return JSONResponse(content={
                "status": "success",
                "character_id": character_id,
                "image_url": f"/{filename}",
                "character_data": GENERATED_ASSETS["characters"][character_id]
            })
    
    return JSONResponse(content={"status": "error", "message": "Failed to generate character"})

@app.post("/generate_scene")
async def generate_scene(
    scene_name: str = Form(...),
    scene_description: str = Form(...),
    scene_time: str = Form("day"),
    scene_lighting: str = Form("natural")
):
    prompt = f"""
    Generate an establishing shot of the scene: {scene_name}
    Scene details: {scene_description}
    Time of day: {scene_time}
    Lighting: {scene_lighting}
    Art style: {GENERATED_ASSETS["storyline"]["art_style"]}
    Camera style: {GENERATED_ASSETS["storyline"]["camera_style"]} - wide establishing shot
    
    Important requirements:
    - Consistent environment details
    - Clear landmarks that can be recognized in other shots
    - Proper lighting that matches the time of day
    - No characters in this shot
    - High resolution and detailed
    """
    
    response = client.models.generate_content(
        model="gemini-2.0-flash-preview-image-generation",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=['TEXT', 'IMAGE']
        )
    )
    
    scene_id = str(uuid.uuid4())
    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            image = Image.open(BytesIO((part.inline_data.data)))
            filename = f"static/scenes/{scene_id}.png"
            image.save(filename)
            
            GENERATED_ASSETS["scenes"][scene_id] = {
                "name": scene_name,
                "description": scene_description,
                "time": scene_time,
                "lighting": scene_lighting,
                "image_path": filename
            }
            
            return JSONResponse(content={
                "status": "success",
                "scene_id": scene_id,
                "image_url": f"/{filename}",
                "scene_data": GENERATED_ASSETS["scenes"][scene_id]
            })
    
    return JSONResponse(content={"status": "error", "message": "Failed to generate scene"})

@app.post("/generate_frame")
async def generate_frame(
    frame_description: str = Form(...),
    scene_id: str = Form(...),
    character_ids: List[str] = Form(...),
    character_expressions: List[str] = Form(...),
    character_positions: List[str] = Form(...),
    camera_angle: str = Form("medium")
):
    scene = GENERATED_ASSETS["scenes"][scene_id]
    characters = [GENERATED_ASSETS["characters"][cid] for cid in character_ids]
    
    character_prompts = []
    for i, char in enumerate(characters):
        character_prompts.append(
            f"{char['name']} ({char['type']}) wearing {char['outfit']} "
            f"with {character_expressions[i]} expression, positioned {character_positions[i]}"
        )
    
    prompt = f"""
    Generate a storyboard frame for our {GENERATED_ASSETS["storyline"]["genre"]} story.
    
    Scene: {scene['name']} - {scene['description']}
    Time: {scene['time']} with {scene['lighting']} lighting
    Camera: {camera_angle} shot ({GENERATED_ASSETS["storyline"]["camera_style"]})
    
    Characters in scene:
    {', '.join(character_prompts)}
    
    Action: {frame_description}
    
    Art style: {GENERATED_ASSETS["storyline"]["art_style"]}
    
    Critical requirements:
    - Maintain exact character appearances from reference images
    - Keep scene details consistent with establishing shot
    - Ensure lighting matches scene time
    - Show the specific action clearly
    - Maintain visual continuity with previous frames
    - High resolution and detailed
    """
    
    response = client.models.generate_content(
        model="gemini-2.0-flash-preview-image-generation",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=['TEXT', 'IMAGE']
        )
    )
    
    frame_id = str(uuid.uuid4())
    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            image = Image.open(BytesIO((part.inline_data.data)))
            filename = f"static/frames/{frame_id}.png"
            image.save(filename)
            
            frame_data = {
                "frame_id": frame_id,
                "description": frame_description,
                "scene_id": scene_id,
                "character_ids": character_ids,
                "expressions": character_expressions,
                "positions": character_positions,
                "camera_angle": camera_angle,
                "image_path": filename,
                "order": len(GENERATED_ASSETS["frames"])
            }
            
            GENERATED_ASSETS["frames"].append(frame_data)
            
            return JSONResponse(content={
                "status": "success",
                "frame_id": frame_id,
                "image_url": f"/{filename}",
                "frame_data": frame_data
            })
    
    return JSONResponse(content={"status": "error", "message": "Failed to generate frame"})

@app.post("/generate_video")
async def generate_video():
    video_prompt = f"""
    Create a 8-second video sequence based on the following storyboard frames:
    
    Story Title: {GENERATED_ASSETS["storyline"]["title"]}
    Genre: {GENERATED_ASSETS["storyline"]["genre"]}
    Theme: {GENERATED_ASSETS["storyline"]["theme"]}
    Art Style: {GENERATED_ASSETS["storyline"]["art_style"]}
    Camera Style: {GENERATED_ASSETS["storyline"]["camera_style"]}
    
    Scene Sequence:
    """
    
    for i, frame in enumerate(sorted(GENERATED_ASSETS["frames"], key=lambda x: x["order"])):
        scene = GENERATED_ASSETS["scenes"][frame["scene_id"]]
        characters = [GENERATED_ASSETS["characters"][cid] for cid in frame["character_ids"]]
        
        video_prompt += f"""
        Frame {i+1}:
        - Scene: {scene['name']} ({scene['time']}, {scene['lighting']} lighting)
        - Characters: {', '.join([f"{c['name']} ({c['type']})" for c in characters])}
        - Action: {frame['description']}
        - Camera: {frame['camera_angle']} shot
        """
    
    video_prompt += """
    Additional Requirements:
    - Smooth transitions between shots
    - Appropriate ambient sounds matching each scene
    - Character-specific sounds (voices, footsteps, etc.)
    - 8-second total duration
    - High quality cinematic output
    - Include title card at beginning
    - Include credits at end
    """
    
    # Generate video (using Veo when available)
    operation = client.models.generate_videos(
        model="veo-3.0-generate-preview",
        prompt=video_prompt,
    )
    
    while not operation.done:
        time.sleep(5)
        operation = client.operations.get(operation)
    
    try:
        if 'generateVideoResponse' in operation.response:
            generated_samples = operation.response['generateVideoResponse']['generatedSamples']
            for n, sample in enumerate(generated_samples):
                video_uri = sample['video']['uri']
                
                api_key = GEMINI_API_KEY
                if api_key:
                    download_url = f"{video_uri}&key={api_key}"
                    response = requests.get(download_url)
                    
                    if response.status_code == 200:
                        filename = f"static/generated/final_video_{n}.mp4"
                        with open(filename, "wb") as f:
                            f.write(response.content)
                        
                        GENERATED_ASSETS["final_video"] = {
                            "video_path": filename,
                            "prompt": video_prompt
                        }
                        
                        return JSONResponse(content={
                            "status": "success",
                            "video_url": f"/{filename}",
                            "prompt": video_prompt
                        })
    
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)})
    
    return JSONResponse(content={"status": "error", "message": "Video generation failed"})

@app.get("/get_story_data")
async def get_story_data():
    return JSONResponse(content=GENERATED_ASSETS)

@app.get("/download_report")
async def download_report():
    report = {
        "story_metadata": GENERATED_ASSETS["storyline"],
        "characters": GENERATED_ASSETS["characters"],
        "scenes": GENERATED_ASSETS["scenes"],
        "frames": GENERATED_ASSETS["frames"],
        "video_prompt": GENERATED_ASSETS["final_video"]["prompt"] if GENERATED_ASSETS["final_video"] else None
    }
    
    filename = "static/generated/story_report.json"
    with open(filename, "w") as f:
        json.dump(report, f, indent=2)
    
    return FileResponse(filename, filename="storyboard_report.json")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)