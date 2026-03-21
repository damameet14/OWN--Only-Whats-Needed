import asyncio
import httpx
import websockets
import json

async def test_export():
    async with httpx.AsyncClient() as client:
        # Assuming project 1 exists and has subtitle data
        resp = await client.post("http://localhost:8000/api/projects/1/export", json={"format": "MP4 (H.264)"})
        if resp.status_code != 200:
            print("Failed to start export:", resp.text)
            return
        
        task_id = resp.json()["task_id"]
        print(f"Export started: {task_id}")
        
        uri = f"ws://localhost:8000/ws/progress/{task_id}"
        async with websockets.connect(uri) as ws:
            while True:
                msg_str = await ws.recv()
                msg = json.loads(msg_str)
                print("Received:", msg)
                if msg["type"] in ("complete", "error"):
                    break

asyncio.run(test_export())
