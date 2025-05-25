import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from typing import Optional

import cv2
import numpy as np
from aiohttp import web
import aiortc
from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaBlackhole, MediaPlayer, MediaRecorder
from av import VideoFrame

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("phone_screen_viewer")

# HTML页面内容
HTML_CONTENT = """
<!DOCTYPE html>
<html>
<head>
    <title>手机屏幕镜像</title>
    <style>
        body {
            margin: 0;
            padding: 20px;
            background: #1a1a1a;
            color: white;
            font-family: Arial, sans-serif;
        }
        #video {
            width: 100%;
            max-width: 1280px;
            margin: 0 auto;
            display: block;
            background: #000;
        }
        .container {
            max-width: 1280px;
            margin: 0 auto;
        }
        h1 {
            text-align: center;
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>手机屏幕镜像</h1>
        <video id="video" autoplay playsinline></video>
    </div>

    <script>
        const video = document.getElementById('video');
        const pc = new RTCPeerConnection();

        pc.ontrack = function(event) {
            if (event.track.kind === 'video') {
                video.srcObject = event.streams[0];
            }
        };

        async function start() {
            try {
                const offer = await pc.createOffer();
                await pc.setLocalDescription(offer);

                const response = await fetch('/offer', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        sdp: pc.localDescription.sdp,
                        type: pc.localDescription.type
                    })
                });

                const answer = await response.json();
                await pc.setRemoteDescription(answer);
            } catch (e) {
                console.error(e);
            }
        }

        start();
    </script>
</body>
</html>
"""

class PhoneScreenTrack(MediaStreamTrack):
    kind = "video"

    def __init__(self):
        super().__init__()
        self.frame_count = 0
        self.last_frame_time = time.time()
        self.fps = 30  # 目标帧率

    async def recv(self):
        try:
            # 使用ADB命令截图
            subprocess.run(['adb', 'shell', 'screencap', '-p', '/sdcard/screen.png'], 
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(['adb', 'pull', '/sdcard/screen.png', 'temp_screen.png'],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # 读取图片
            frame = cv2.imread('temp_screen.png')
            if frame is not None:
                # 调整图片大小
                frame = cv2.resize(frame, (1280, 720))
                
                # 转换为VideoFrame
                video_frame = VideoFrame.from_ndarray(frame, format="bgr24")
                video_frame.pts = self.frame_count
                video_frame.time_base = "1/1000"
                self.frame_count += 1

                # 控制帧率
                current_time = time.time()
                elapsed = current_time - self.last_frame_time
                if elapsed < 1.0/self.fps:
                    await asyncio.sleep(1.0/self.fps - elapsed)
                self.last_frame_time = time.time()

                return video_frame
            else:
                # 如果读取失败，返回黑屏
                frame = np.zeros((720, 1280, 3), dtype=np.uint8)
                video_frame = VideoFrame.from_ndarray(frame, format="bgr24")
                video_frame.pts = self.frame_count
                video_frame.time_base = "1/1000"
                self.frame_count += 1
                return video_frame

        except Exception as e:
            logger.error(f"Error capturing screen: {e}")
            # 发生错误时返回黑屏
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            video_frame = VideoFrame.from_ndarray(frame, format="bgr24")
            video_frame.pts = self.frame_count
            video_frame.time_base = "1/1000"
            self.frame_count += 1
            return video_frame

async def index(request):
    return web.Response(text=HTML_CONTENT, content_type='text/html')

async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(
        sdp=params["sdp"],
        type=params["type"]
    )

    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        if pc.connectionState == "failed":
            await pc.close()
            pcs.discard(pc)

    @pc.on("track")
    def on_track(track):
        if track.kind == "video":
            pc.addTrack(PhoneScreenTrack())

    # 处理offer
    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.Response(
        content_type="application/json",
        text=json.dumps({
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type
        })
    )

pcs = set()

async def on_shutdown(app):
    # 关闭所有peer connections
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()

if __name__ == "__main__":
    app = web.Application()
    app.router.add_get("/", index)  # 添加首页路由
    app.router.add_post("/offer", offer)
    app.on_shutdown.append(on_shutdown)
    web.run_app(app, host="0.0.0.0", port=8080) 